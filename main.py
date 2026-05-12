import os
import json
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
    # Detailed execution log for debugging
    execution_log = []

    def log_step(step_name, status, details=None):
        """Log each step with status and optional details"""
        log_entry = {
            "step": step_name,
            "status": status,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
        if details:
            log_entry["details"] = details
        execution_log.append(log_entry)
        print(f"[{status.upper()}] {step_name}")
        if details:
            print(f"  Details: {details}")
    # Validate required fields
    log_step("validate_required_fields", "started")
    required_fields = [
        'business_name', 'street', 'city', 'region', 'postal_code', 'country',
        'business_type', 'tax_id', 'website', 'first_name', 'last_name', 'email', 'phone'
    ]
    missing_fields = [field for field in required_fields if field not in customer_info]
    if missing_fields:
        log_step("validate_required_fields", "failed", {"missing_fields": missing_fields})
        print(f"ERROR: Missing required fields in customer_info: {', '.join(missing_fields)}")
        return {"execution_log": execution_log, "error": f"Missing required fields: {', '.join(missing_fields)}"}
    log_step("validate_required_fields", "success")

    # Validate file exists only if a path was provided
    if file_path:
        log_step("validate_file_path", "started", {"file_path": file_path})
        if not os.path.exists(file_path):
            log_step("validate_file_path", "failed", {"error": "File not found"})
            print(f"ERROR: File not found: {file_path}")
            return {"execution_log": execution_log, "error": f"File not found: {file_path}"}
        log_step("validate_file_path", "success")

    try:
        # --- DYNAMIC LOOKUPS ---
        log_step("lookup_policies", "started")
        policies = client.trusthub.v1.policies.list()
        SECONDARY_POLICY_SID = next((p.sid for p in policies if p.friendly_name == "Secondary Customer Profile of type Business"), None)
        SHAKEN_POLICY_SID = next((p.sid for p in policies if p.friendly_name == "SHAKEN/STIR"), None)

        # Validate required policies exist before proceeding
        if not SECONDARY_POLICY_SID:
            log_step("lookup_policies", "failed", {"error": "Secondary Customer Profile policy not found"})
            print("ERROR: Could not find 'Secondary Customer Profile of type Business' policy.")
            return {"execution_log": execution_log, "error": "Secondary Customer Profile policy not found"}
        if not SHAKEN_POLICY_SID:
            log_step("lookup_policies", "failed", {"error": "SHAKEN/STIR policy not found"})
            print("ERROR: Could not find 'SHAKEN/STIR' policy.")
            return {"execution_log": execution_log, "error": "SHAKEN/STIR policy not found"}

        log_step("lookup_policies", "success", {
            "secondary_policy_sid": SECONDARY_POLICY_SID,
            "shaken_policy_sid": SHAKEN_POLICY_SID
        })
        print(f"Found Secondary Policy: {SECONDARY_POLICY_SID}")
        print(f"Found SHAKEN Policy: {SHAKEN_POLICY_SID}")

        # --- IDEMPOTENCY CHECK: Look for existing profile and trust product ---
        log_step("check_existing_resources", "started")
        existing_profile = None
        existing_trust_product = None

        # Check for existing customer profile with matching business name
        profiles = client.trusthub.v1.customer_profiles.list(
            policy_sid=SECONDARY_POLICY_SID,
            limit=100
        )
        for p in profiles:
            if customer_info['business_name'] in p.friendly_name:
                existing_profile = p
                log_step("check_existing_resources", "info", {
                    "found_existing_profile": True,
                    "profile_sid": p.sid,
                    "profile_status": p.status
                })
                print(f"Found existing Customer Profile: {p.sid} (status: {p.status})")
                break

        # Check for existing trust product with matching business name
        trust_products = client.trusthub.v1.trust_products.list(
            policy_sid=SHAKEN_POLICY_SID,
            limit=100
        )
        for tp in trust_products:
            if customer_info['business_name'] in tp.friendly_name:
                existing_trust_product = tp
                log_step("check_existing_resources", "info", {
                    "found_existing_trust_product": True,
                    "trust_product_sid": tp.sid,
                    "trust_product_status": tp.status
                })
                print(f"Found existing Trust Product: {tp.sid} (status: {tp.status})")
                break

        if existing_profile and existing_trust_product:
            log_step("check_existing_resources", "success", {
                "action": "reusing_existing_resources",
                "profile_sid": existing_profile.sid,
                "trust_product_sid": existing_trust_product.sid
            })
            print("\nWARNING: Resources already exist. Checking phone number assignments...")

            # Check which phone numbers are already assigned
            # Convert single phone number to list for backwards compatibility
            if isinstance(target_phone_numbers, str):
                target_phone_numbers = [target_phone_numbers]

            # Lookup all phone number SIDs
            log_step("lookup_phone_numbers", "started", {"phone_count": len(target_phone_numbers)})
            phone_number_sids = []
            not_found_numbers = []
            for phone_number in target_phone_numbers:
                number_list = client.incoming_phone_numbers.list(phone_number=phone_number, limit=1)
                if number_list:
                    phone_number_sids.append((phone_number, number_list[0].sid))
                else:
                    not_found_numbers.append(phone_number)

            if not phone_number_sids:
                log_step("lookup_phone_numbers", "failed", {
                    "error": "No valid phone numbers found",
                    "not_found": not_found_numbers
                })
                return {"execution_log": execution_log, "error": "No valid phone numbers found in account"}

            log_step("lookup_phone_numbers", "success", {
                "found_count": len(phone_number_sids),
                "not_found_count": len(not_found_numbers)
            })

            # Assign any unassigned phone numbers
            log_step("assign_new_phone_numbers", "started")
            assigned_numbers = []
            failed_numbers = []
            already_assigned = []

            for phone_number, phone_sid in phone_number_sids:
                try:
                    client.trusthub.v1.trust_products(existing_trust_product.sid).customer_profiles_channel_endpoint_assignment.create(
                        channel_endpoint_type="phone-number",
                        channel_endpoint_sid=phone_sid
                    )
                    print(f"  ✓ Newly assigned {phone_number}")
                    assigned_numbers.append(phone_number)
                except TwilioRestException as e:
                    if "already has a trust product" in str(e).lower():
                        print(f"  INFO: {phone_number} already assigned")
                        already_assigned.append(phone_number)
                    else:
                        print(f"  ✗ Failed to assign {phone_number}: {e}")
                        failed_numbers.append((phone_number, str(e)))

            log_step("assign_new_phone_numbers", "success", {
                "newly_assigned": len(assigned_numbers),
                "already_assigned": len(already_assigned),
                "failed": len(failed_numbers)
            })

            return {
                "profile_sid": existing_profile.sid,
                "trust_product_sid": existing_trust_product.sid,
                "assigned_numbers": assigned_numbers + already_assigned,
                "failed_numbers": failed_numbers,
                "total_requested": len(phone_number_sids),
                "execution_log": execution_log,
                "reused_existing": True
            }
        else:
            log_step("check_existing_resources", "success", {
                "action": "creating_new_resources",
                "existing_profile": existing_profile.sid if existing_profile else None,
                "existing_trust_product": existing_trust_product.sid if existing_trust_product else None
            })
            print("No existing resources found. Creating new resources...")

        # Convert single phone number to list for backwards compatibility
        if isinstance(target_phone_numbers, str):
            target_phone_numbers = [target_phone_numbers]

        # Lookup all phone number SIDs
        log_step("lookup_phone_numbers", "started", {"phone_count": len(target_phone_numbers)})
        phone_number_sids = []
        not_found_numbers = []
        for phone_number in target_phone_numbers:
            number_list = client.incoming_phone_numbers.list(phone_number=phone_number, limit=1)
            if number_list:
                phone_number_sids.append((phone_number, number_list[0].sid))
                print(f"Found Phone: {phone_number} -> {number_list[0].sid}")
            else:
                not_found_numbers.append(phone_number)
                print(f"WARNING: Could not find phone number {phone_number} in account. Skipping.")

        if not phone_number_sids:
            log_step("lookup_phone_numbers", "failed", {
                "error": "No valid phone numbers found",
                "not_found": not_found_numbers
            })
            print("ERROR: No valid phone numbers found in account.")
            return {"execution_log": execution_log, "error": "No valid phone numbers found in account"}

        log_step("lookup_phone_numbers", "success", {
            "found_count": len(phone_number_sids),
            "not_found_count": len(not_found_numbers),
            "not_found_numbers": not_found_numbers
        })
        print(f"Total phone numbers to register: {len(phone_number_sids)}")

        # STEP 1: CREATE ADDRESS
        log_step("create_address", "started")
        address = client.addresses.create(
            customer_name=customer_info['business_name'],
            street=customer_info['street'],
            city=customer_info['city'],
            region=customer_info['region'],
            postal_code=customer_info['postal_code'],
            iso_country=customer_info['country']
        )
        log_step("create_address", "success", {"address_sid": address.sid})
        print(f"Created Address: {address.sid}")

        # STEP 2: CREATE SUPPORTING DOCUMENTS
        # Document A: Address Proof (links to Address SID)
        # Note: attributes must be passed as JSON string for Twilio API
        log_step("create_address_document", "started")
        address_doc = client.trusthub.v1.supporting_documents.create(
            friendly_name=f"Address - {customer_info['business_name']}",
            type="customer_profile_address",
            attributes=json.dumps({"address_sids": [address.sid]})
        )
        log_step("create_address_document", "success", {"address_doc_sid": address_doc.sid})

        # Document B: Identity Proof (EIN / Business Registration)
        # A physical file upload is optional — attributes alone are sufficient.
        log_step("create_identity_document", "started")
        identity_attributes = json.dumps({
            "business_name": customer_info['business_name'],
            "document_number": customer_info['tax_id']
        })

        if file_path:
            print(f"Uploading {file_path}...")
            with open(file_path, 'rb') as f:
                identity_doc = client.trusthub.v1.supporting_documents.create(
                    friendly_name="Business Identity Proof",
                    type="business_registration",
                    attributes=identity_attributes,
                    file=f
                )
            log_step("create_identity_document", "success", {
                "identity_doc_sid": identity_doc.sid,
                "with_file": True
            })
            print(f"Identity Document Uploaded: {identity_doc.sid}")
        else:
            identity_doc = client.trusthub.v1.supporting_documents.create(
                friendly_name="Business Identity Proof",
                type="business_registration",
                attributes=identity_attributes
            )
            log_step("create_identity_document", "success", {
                "identity_doc_sid": identity_doc.sid,
                "with_file": False
            })
            print(f"Created Identity Document (no file): {identity_doc.sid}")

        # STEP 3: CREATE END USERS (Three Required per documentation)
        # 1. Business Legal Info (Required attributes: identity, industry, regions)
        log_step("create_business_info_end_user", "started")
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
        log_step("create_business_info_end_user", "success", {"biz_info_sid": biz_info.sid})

        # 2. Authorized Representative 1
        log_step("create_rep1_end_user", "started")
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
        log_step("create_rep1_end_user", "success", {"rep1_sid": rep1.sid})

        # 3. Authorized Representative 2 (The policy requires two distinct rep assignments)
        # If rep2 data not provided, use rep1 data (common for small businesses)
        log_step("create_rep2_end_user", "started")
        rep2_data = customer_info.get('rep2', rep1_data)
        rep2 = client.trusthub.v1.end_users.create(
            friendly_name="Secondary Authorized Representative",
            type="authorized_representative_2",
            attributes=rep2_data
        )
        log_step("create_rep2_end_user", "success", {"rep2_sid": rep2.sid})
        print("Created End User entities (Business Info, Rep 1, and Rep 2).")

        # STEP 4: CREATE SECONDARY CUSTOMER PROFILE
        log_step("create_customer_profile", "started")
        profile = client.trusthub.v1.customer_profiles.create(
            friendly_name=f"Secondary Profile: {customer_info['business_name']}",
            email=customer_info['email'],
            policy_sid=SECONDARY_POLICY_SID
        )
        log_step("create_customer_profile", "success", {"profile_sid": profile.sid})

        # STEP 5: ASSIGN ALL ENTITIES TO THE PROFILE
        log_step("assign_entities_to_profile", "started")
        entities_to_assign = [biz_info.sid, rep1.sid, rep2.sid, address_doc.sid, identity_doc.sid]
        for i, sid in enumerate(entities_to_assign):
            client.trusthub.v1.customer_profiles(profile.sid).customer_profiles_entity_assignments.create(object_sid=sid)
        log_step("assign_entities_to_profile", "success", {
            "entities_assigned": len(entities_to_assign),
            "entity_sids": entities_to_assign
        })

        # STEP 6: SUBMIT PROFILE FOR REVIEW
        log_step("submit_profile_for_review", "started")
        client.trusthub.v1.customer_profiles(profile.sid).update(status="pending-review")
        log_step("submit_profile_for_review", "success")
        print(f"Secondary Customer Profile {profile.sid} submitted for review.")

        # STEP 7: CREATE STIR/SHAKEN TRUST PRODUCT
        log_step("create_trust_product", "started")
        trust_product = client.trusthub.v1.trust_products.create(
            friendly_name=f"STIR/SHAKEN: {customer_info['business_name']}",
            email=customer_info['email'],
            policy_sid=SHAKEN_POLICY_SID
        )
        log_step("create_trust_product", "success", {"trust_product_sid": trust_product.sid})

        # STEP 8: LINK SECONDARY PROFILE TO TRUST PRODUCT
        log_step("link_profile_to_trust_product", "started")
        client.trusthub.v1.trust_products(trust_product.sid).trust_products_entity_assignments.create(object_sid=profile.sid)
        log_step("link_profile_to_trust_product", "success")

        # STEP 9: ASSIGN ALL PHONE NUMBERS TO TRUST PRODUCT (Channel Endpoints)
        log_step("assign_phone_numbers", "started", {"phone_count": len(phone_number_sids)})
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

        log_step("assign_phone_numbers", "success", {
            "assigned_count": len(assigned_numbers),
            "failed_count": len(failed_numbers),
            "assigned_numbers": assigned_numbers,
            "failed_numbers": [{"number": num, "error": err} for num, err in failed_numbers]
        })

        # STEP 10: SUBMIT TRUST PRODUCT FOR REVIEW
        log_step("submit_trust_product_for_review", "started")
        client.trusthub.v1.trust_products(trust_product.sid).update(status="pending-review")
        log_step("submit_trust_product_for_review", "success")
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

        result = {
            "profile_sid": profile.sid,
            "trust_product_sid": trust_product.sid,
            "assigned_numbers": assigned_numbers,
            "failed_numbers": failed_numbers,
            "total_requested": len(phone_number_sids),
            "execution_log": execution_log
        }
        log_step("onboarding_complete", "success")
        return result

    except TwilioRestException as e:
        log_step("onboarding_failed", "error", {
            "error_type": "TwilioRestException",
            "error_message": str(e),
            "error_code": getattr(e, 'code', None),
            "error_status": getattr(e, 'status', None)
        })
        print(f"\nTwilio API Error: {e}")
        print("The onboarding process was interrupted. Some resources may have been created.")
        return {"execution_log": execution_log, "error": str(e), "error_type": "TwilioRestException"}
    except KeyError as e:
        log_step("onboarding_failed", "error", {
            "error_type": "KeyError",
            "error_message": f"Missing required field: {e}"
        })
        print(f"\nMissing required field in customer_info: {e}")
        return {"execution_log": execution_log, "error": f"Missing required field: {e}", "error_type": "KeyError"}
    except Exception as e:
        log_step("onboarding_failed", "error", {
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        print(f"\nUnexpected error: {type(e).__name__}: {e}")
        return {"execution_log": execution_log, "error": str(e), "error_type": type(e).__name__}

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