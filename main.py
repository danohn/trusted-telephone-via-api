import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# 1. Setup Credentials
ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')

if not ACCOUNT_SID or not AUTH_TOKEN:
    raise ValueError(
        "Missing Twilio credentials. Please set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables."
    )

client = Client(ACCOUNT_SID, AUTH_TOKEN)

def onboard_isv_customer(customer_info, target_phone_numbers, file_path=None):
    """
    Onboard an ISV customer to Twilio Trust Hub.

    Args:
        customer_info: Dictionary containing customer details
        target_phone_numbers: List of phone numbers to register (e.g., ["+14155556789", "+14155556790"])
        file_path: Optional path to a business license/identity document (PDF, JPEG, or PNG).
                   If omitted, the business_registration document is created using attributes only.

    Returns:
        dict: Contains created resource SIDs (profile_sid, trust_product_sid, phone_numbers_assigned)
              Returns None if operation fails
    """
    # Validate required fields
    required_fields = [
        'business_name', 'street', 'city', 'region', 'postal_code', 'country',
        'business_type', 'tax_id', 'website', 'first_name', 'last_name', 'email', 'phone'
    ]
    missing_fields = [field for field in required_fields if field not in customer_info]
    if missing_fields:
        print(f"ERROR: Missing required fields in customer_info: {', '.join(missing_fields)}")
        return None

    # Validate file exists only if a path was provided
    if file_path and not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        return None

    try:
        # --- DYNAMIC LOOKUPS ---
        policies = client.trusthub.v1.policies.list()
        SECONDARY_POLICY_SID = next((p.sid for p in policies if p.friendly_name == "Secondary Customer Profile of type Business"), None)
        SHAKEN_POLICY_SID = next((p.sid for p in policies if p.friendly_name == "SHAKEN/STIR"), None)

        # Validate required policies exist before proceeding
        if not SECONDARY_POLICY_SID:
            print("ERROR: Could not find 'Secondary Customer Profile of type Business' policy.")
            return
        if not SHAKEN_POLICY_SID:
            print("ERROR: Could not find 'SHAKEN/STIR' policy.")
            return

        print(f"Found Secondary Policy: {SECONDARY_POLICY_SID}")
        print(f"Found SHAKEN Policy: {SHAKEN_POLICY_SID}")

        # Convert single phone number to list for backwards compatibility
        if isinstance(target_phone_numbers, str):
            target_phone_numbers = [target_phone_numbers]

        # Lookup all phone number SIDs
        phone_number_sids = []
        for phone_number in target_phone_numbers:
            number_list = client.incoming_phone_numbers.list(phone_number=phone_number, limit=1)
            if number_list:
                phone_number_sids.append((phone_number, number_list[0].sid))
                print(f"Found Phone: {phone_number} -> {number_list[0].sid}")
            else:
                print(f"WARNING: Could not find phone number {phone_number} in account. Skipping.")

        if not phone_number_sids:
            print("ERROR: No valid phone numbers found in account.")
            return

        print(f"Total phone numbers to register: {len(phone_number_sids)}")

        # STEP 1: CREATE ADDRESS
        address = client.addresses.create(
            customer_name=customer_info['business_name'],
            street=customer_info['street'],
            city=customer_info['city'],
            region=customer_info['region'],
            postal_code=customer_info['postal_code'],
            iso_country=customer_info['country']
        )
        print(f"Created Address: {address.sid}")

        # STEP 2: CREATE SUPPORTING DOCUMENTS
        # Document A: Address Proof (links to Address SID)
        # Note: friendly_name is omitted for customer_profile_address type as it's auto-generated
        address_doc = client.trusthub.v1.supporting_documents.create(
            type="customer_profile_address",
            attributes={"address_sids": [address.sid]}
        )

        # Document B: Identity Proof (EIN / Business Registration)
        # A physical file upload is optional — attributes alone are sufficient.
        if file_path:
            print(f"Uploading {file_path}...")
            with open(file_path, 'rb') as f:
                identity_doc = client.trusthub.v1.supporting_documents.create(
                    friendly_name="Business Identity Proof",
                    type="business_registration",
                    attributes={
                        "business_name": customer_info['business_name'],
                        "document_number": customer_info['tax_id']
                    },
                    file=f
                )
            print(f"Identity Document Uploaded: {identity_doc.sid}")
        else:
            identity_doc = client.trusthub.v1.supporting_documents.create(
                friendly_name="Business Identity Proof",
                type="business_registration",
                attributes={
                    "business_name": customer_info['business_name'],
                    "document_number": customer_info['tax_id']
                }
            )
            print(f"Created Identity Document (no file): {identity_doc.sid}")

        # STEP 3: CREATE END USERS (Three Required per documentation)
        # 1. Business Legal Info (Required attributes: identity, industry, regions)
        biz_info = client.trusthub.v1.end_users.create(
            friendly_name="Business Legal Information",
            type="customer_profile_business_information",
            attributes={
                "business_name": customer_info['business_name'],
                "business_type": customer_info['business_type'],
                "business_registration_number": customer_info['tax_id'],
                "business_registration_identifier": "EIN",
                "business_identity": "direct_customer",
                "business_industry": customer_info.get('business_industry', 'TECHNOLOGY'),
                "business_regions_of_operation": customer_info.get('business_regions_of_operation', 'USA_AND_CANADA'),
                "website_url": customer_info['website']
            }
        )

        # 2. Authorized Representative 1
        rep1_data = customer_info.get('rep1', {
            "first_name": customer_info['first_name'],
            "last_name": customer_info['last_name'],
            "email": customer_info['email'],
            "phone_number": customer_info['phone'],
            "job_position": customer_info.get('job_position', 'Director')
        })
        rep1 = client.trusthub.v1.end_users.create(
            friendly_name="Primary Authorized Representative",
            type="authorized_representative_1",
            attributes=rep1_data
        )

        # 3. Authorized Representative 2 (The policy requires two distinct rep assignments)
        # If rep2 data not provided, use rep1 data (common for small businesses)
        rep2_data = customer_info.get('rep2', rep1_data)
        rep2 = client.trusthub.v1.end_users.create(
            friendly_name="Secondary Authorized Representative",
            type="authorized_representative_2",
            attributes=rep2_data
        )
        print("Created End User entities (Business Info, Rep 1, and Rep 2).")

        # STEP 4: CREATE SECONDARY CUSTOMER PROFILE
        profile = client.trusthub.v1.customer_profiles.create(
            friendly_name=f"Secondary Profile: {customer_info['business_name']}",
            email=customer_info['email'],
            policy_sid=SECONDARY_POLICY_SID
        )

        # STEP 5: ASSIGN ALL ENTITIES TO THE PROFILE
        entities_to_assign = [biz_info.sid, rep1.sid, rep2.sid, address_doc.sid, identity_doc.sid]
        for sid in entities_to_assign:
            client.trusthub.v1.customer_profiles(profile.sid).customer_profiles_entity_assignments.create(object_sid=sid)

        # STEP 6: SUBMIT PROFILE FOR REVIEW
        client.trusthub.v1.customer_profiles(profile.sid).update(status="pending-review")
        print(f"Secondary Customer Profile {profile.sid} submitted for review.")

        # STEP 7: CREATE STIR/SHAKEN TRUST PRODUCT
        trust_product = client.trusthub.v1.trust_products.create(
            friendly_name=f"STIR/SHAKEN: {customer_info['business_name']}",
            email=customer_info['email'],
            policy_sid=SHAKEN_POLICY_SID
        )

        # STEP 8: LINK SECONDARY PROFILE TO TRUST PRODUCT
        client.trusthub.v1.trust_products(trust_product.sid).trust_products_entity_assignments.create(object_sid=profile.sid)

        # STEP 9: ASSIGN ALL PHONE NUMBERS TO TRUST PRODUCT (Channel Endpoints)
        print(f"Assigning {len(phone_number_sids)} phone number(s) to Trust Product...")
        assigned_numbers = []
        failed_numbers = []

        for phone_number, phone_sid in phone_number_sids:
            try:
                client.trusthub.v1.trust_products(trust_product.sid).customer_profiles_channel_endpoint_assignment.create(
                    channel_endpoint_type="phone-number",
                    channel_endpoint_sid=phone_sid
                )
                print(f"  ✓ Assigned {phone_number}")
                assigned_numbers.append(phone_number)
            except TwilioRestException as e:
                print(f"  ✗ Failed to assign {phone_number}: {e}")
                failed_numbers.append((phone_number, str(e)))

        # STEP 10: SUBMIT TRUST PRODUCT FOR REVIEW
        client.trusthub.v1.trust_products(trust_product.sid).update(status="pending-review")
        print(f"STIR/SHAKEN Trust Product {trust_product.sid} submitted for review.")

        # Print summary
        print("\n" + "="*60)
        print("--- ONBOARDING COMPLETE ---")
        print(f"Customer Profile SID: {profile.sid}")
        print(f"Trust Product SID: {trust_product.sid}")
        print(f"Phone Numbers Assigned: {len(assigned_numbers)}/{len(phone_number_sids)}")
        if failed_numbers:
            print(f"Failed Assignments: {len(failed_numbers)}")
            for num, error in failed_numbers:
                print(f"  - {num}: {error}")
        print("="*60)

        return {
            "profile_sid": profile.sid,
            "trust_product_sid": trust_product.sid,
            "assigned_numbers": assigned_numbers,
            "failed_numbers": failed_numbers,
            "total_requested": len(phone_number_sids)
        }

    except TwilioRestException as e:
        print(f"\nTwilio API Error: {e}")
        print("The onboarding process was interrupted. Some resources may have been created.")
        return None
    except KeyError as e:
        print(f"\nMissing required field in customer_info: {e}")
        return None
    except Exception as e:
        print(f"\nUnexpected error: {type(e).__name__}: {e}")
        return None

if __name__ == "__main__":
    # Example usage - Basic configuration
    data = {
        # Required fields
        "business_name": "Acme Corp",
        "street": "123 Twilio Lane",
        "city": "San Francisco",
        "region": "CA",
        "postal_code": "94105",
        "country": "US",
        "business_type": "Corporation",
        "tax_id": "12-3456789",
        "website": "https://acme.example",
        "first_name": "John",
        "last_name": "Doe",
        "email": "compliance@acme.example",
        "phone": "+14155551234",

        # Optional fields (with defaults shown)
        "business_industry": "TECHNOLOGY",  # Default: TECHNOLOGY
        "business_regions_of_operation": "USA_AND_CANADA",  # Default: USA_AND_CANADA
        "job_position": "Director",  # Default: Director

        # Optional: Separate representative data (if different from primary contact)
        # "rep1": {
        #     "first_name": "John",
        #     "last_name": "Doe",
        #     "email": "john@acme.example",
        #     "phone_number": "+14155551234",
        #     "job_position": "CEO"
        # },
        # "rep2": {
        #     "first_name": "Jane",
        #     "last_name": "Smith",
        #     "email": "jane@acme.example",
        #     "phone_number": "+14155551235",
        #     "job_position": "CFO"
        # }
    }
    # Multiple phone numbers
    PHONES_TO_REGISTER = [
        "+14155556789",
        "+14155556790",
        "+14155556791"
    ]

    # file_path is optional — omit it or pass a path to upload a business licence document
    result = onboard_isv_customer(data, PHONES_TO_REGISTER)
    # result = onboard_isv_customer(data, PHONES_TO_REGISTER, file_path="business_license.pdf")

    if result:
        print(f"\nSuccess! Profile SID: {result['profile_sid']}")
        print(f"Assigned {result['assigned_numbers']} number(s)")