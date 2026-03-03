import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# 1. Setup Credentials
ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
client = Client(ACCOUNT_SID, AUTH_TOKEN)

def onboard_isv_customer(customer_info, target_phone_number, file_path):
    try:
        # --- DYNAMIC LOOKUPS ---
        policies = client.trusthub.v1.policies.list()
        SECONDARY_POLICY_SID = next((p.sid for p in policies if p.friendly_name == "Secondary Customer Profile of type Business"), None)
        SHAKEN_POLICY_SID = next((p.sid for p in policies if p.friendly_name == "SHAKEN/STIR"), None)
        
        number_list = client.incoming_phone_numbers.list(phone_number=target_phone_number, limit=1)
        PHONE_NUMBER_SID = number_list[0].sid if number_list else None

        if not all([SECONDARY_POLICY_SID, SHAKEN_POLICY_SID, PHONE_NUMBER_SID]):
            print("Missing required Policies or Phone Number. Check your friendly names or number formatting.")
            return

        print(f"Found Secondary Policy: {SECONDARY_POLICY_SID}")
        print(f"Found SHAKEN Policy: {SHAKEN_POLICY_SID}")
        print(f"Found Phone SID: {PHONE_NUMBER_SID}")

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
        address_doc = client.trusthub.v1.supporting_documents.create(
            friendly_name="Address Proof",
            type="customer_profile_address",
            attributes={"address_sids": address.sid}
        )

        # Document B: Identity Proof (Physical File Upload - e.g., EIN or Business License)
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
                "business_industry": "TECHNOLOGY",
                "business_regions_of_operation": "USA_AND_CANADA",
                "website_url": customer_info['website']
            }
        )

        # 2. Authorized Representative 1
        rep1 = client.trusthub.v1.end_users.create(
            friendly_name="Primary Authorized Representative",
            type="authorized_representative_1",
            attributes={
                "first_name": customer_info['first_name'],
                "last_name": customer_info['last_name'],
                "email": customer_info['email'],
                "phone_number": customer_info['phone'],
                "job_position": "Director"
            }
        )

        # 3. Authorized Representative 2 (The policy requires two distinct rep assignments)
        rep2 = client.trusthub.v1.end_users.create(
            friendly_name="Secondary Authorized Representative",
            type="authorized_representative_2",
            attributes={
                "first_name": customer_info['first_name'],
                "last_name": customer_info['last_name'],
                "email": customer_info['email'],
                "phone_number": customer_info['phone'],
                "job_position": "Director"
            }
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

        # STEP 9: ASSIGN PHONE NUMBER TO TRUST PRODUCT (Channel Endpoint)
        client.trusthub.v1.trust_products(trust_product.sid).customer_profiles_channel_endpoint_assignment.create(
            channel_endpoint_type="phone-number",
            channel_endpoint_sid=PHONE_NUMBER_SID
        )

        # STEP 10: SUBMIT TRUST PRODUCT FOR REVIEW
        client.trusthub.v1.trust_products(trust_product.sid).update(status="pending-review")
        print(f"STIR/SHAKEN Trust Product {trust_product.sid} submitted for review.")
        print("--- ONBOARDING COMPLETE ---")

    except TwilioRestException as e:
        print(f"Twilio API Error: {e}")
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found locally.")

if __name__ == "__main__":
    # Example usage
    data = {
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
        "phone": "+14155551234"
    }
    FILE_TO_UPLOAD = "business_license.pdf"
    PHONE_TO_REGISTER = "+14155556789"
    
    onboard_isv_customer(data, PHONE_TO_REGISTER, FILE_TO_UPLOAD)