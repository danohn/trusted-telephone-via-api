import os
import json
import re
from urllib.parse import urlparse
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# 1. Setup Credentials
ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
SECONDARY_POLICY_SID_ENV = os.environ.get('TWILIO_SECONDARY_CUSTOMER_PROFILE_POLICY_SID')
SHAKEN_POLICY_SID_ENV = os.environ.get('TWILIO_SHAKEN_STIR_POLICY_SID')
SECONDARY_CUSTOMER_PROFILE_POLICY_SID = "RNdfbf3fae0e1107f8aded0e7cead80bf5"
SHAKEN_STIR_POLICY_SID = "RN7a97559effdf62d00f4298208492a5ea"
VALID_JOB_POSITIONS = {"CEO", "CFO", "VP", "GM", "General Counsel", "Director", "Other"}
VALID_BUSINESS_IDENTITIES = {"direct_customer", "isv_reseller_or_partner", "unknown"}
VALID_BUSINESS_TYPES = {
    "Sole Proprietorship",
    "Partnership",
    "Limited Liability Corporation",
    "Co-operative",
    "Non-profit Corporation",
    "Corporation",
}
VALID_BUSINESS_INDUSTRIES = {
    "AGRICULTURE",
    "AUTOMOTIVE",
    "BANKING",
    "CONSUMER",
    "EDUCATION",
    "ELECTRONICS",
    "ENERGY",
    "ENGINEERING",
    "FAST_MOVING_CONSUMER_GOODS",
    "FINANCIAL",
    "FINTECH",
    "FOOD_AND_BEVERAGE",
    "GOVERNMENT",
    "HEALTHCARE",
    "HOSPITALITY",
    "INSURANCE",
    "JEWELRY",
    "LEGAL",
    "MANUFACTURING",
    "MEDIA",
    "NOT_FOR_PROFIT",
    "OIL_AND_GAS",
    "ONLINE",
    "RAW_MATERIALS",
    "REAL_ESTATE",
    "RELIGION",
    "RETAIL",
    "TECHNOLOGY",
    "TELECOMMUNICATIONS",
    "TRANSPORTATION",
    "TRAVEL",
}
VALID_BUSINESS_REGISTRATION_IDENTIFIERS = {
    "EIN",
    "CBN",
    "CN",
    "ACN",
    "CIN",
    "VAT",
    "VATRN",
    "RN",
    "DUNS",
    "Other",
}
VALID_BUSINESS_REGIONS_OF_OPERATION = {
    "AFRICA",
    "ASIA",
    "EUROPE",
    "LATIN_AMERICA",
    "USA_AND_CANADA",
    "AUSTRALIA",
}
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}
CUSTOMER_PROFILE_SID_RE = re.compile(r"^BU[0-9a-fA-F]{32}$")
E164_PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")

if not ACCOUNT_SID or not AUTH_TOKEN:
    raise ValueError(
        "Missing Twilio credentials. Please set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables."
    )

client = Client(ACCOUNT_SID, AUTH_TOKEN)


def _secondary_policy_sid(primary_profile_sid):
    """
    Use the Secondary Customer Profile policy SID, while still fetching the
    configured Primary Customer Profile to validate it and log its status.
    Allow an env override for accounts that need it.
    """
    primary_profile = client.trusthub.v1.customer_profiles(primary_profile_sid).fetch()
    if SECONDARY_POLICY_SID_ENV:
        return SECONDARY_POLICY_SID_ENV, primary_profile
    return SECONDARY_CUSTOMER_PROFILE_POLICY_SID, primary_profile


def _shaken_stir_policy_sid():
    if SHAKEN_POLICY_SID_ENV:
        return SHAKEN_POLICY_SID_ENV
    return SHAKEN_STIR_POLICY_SID


def _primary_customer_profile_sid(customer_info):
    return (
        customer_info.get("primary_customer_profile_sid")
        or os.environ.get("TWILIO_PRIMARY_CUSTOMER_PROFILE_SID")
    )


def _evaluation_result(evaluation):
    return {
        "evaluation_sid": evaluation.sid,
        "status": evaluation.status,
        "results": evaluation.results,
    }


def _valid_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def onboard_isv_customer(customer_info, target_phone_numbers):
    """
    Onboard an ISV customer to Twilio Trust Hub.

    Args:
        customer_info: Dictionary containing customer details
        target_phone_numbers: List of phone numbers to register (e.g., ["+14155556789", "+14155556790"])

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

    def representative_data(rep_key):
        rep = customer_info.get(rep_key)
        if rep is None:
            rep = {
                "first_name": customer_info["first_name"],
                "last_name": customer_info["last_name"],
                "email": customer_info["email"],
                "phone_number": customer_info["phone"],
            }
        return {
            **rep,
            "business_title": rep.get(
                "business_title",
                customer_info.get("business_title", customer_info.get("job_position", "Director")),
            ),
            "job_position": rep.get("job_position", customer_info.get("job_position", "Director")),
        }

    # Validate required fields
    log_step("validate_required_fields", "started")
    required_fields = [
        'business_name', 'street', 'city', 'region', 'postal_code', 'country',
        'business_type', 'tax_id', 'website', 'email'
    ]
    missing_fields = [field for field in required_fields if field not in customer_info]
    if "rep1" not in customer_info:
        missing_fields.extend(
            field for field in ("first_name", "last_name", "phone") if field not in customer_info
        )
    else:
        missing_fields.extend(
            f"rep1.{field}"
            for field in ("first_name", "last_name", "email", "phone_number")
            if field not in customer_info["rep1"]
        )
    if "rep2" in customer_info:
        missing_fields.extend(
            f"rep2.{field}"
            for field in ("first_name", "last_name", "email", "phone_number")
            if field not in customer_info["rep2"]
        )
    primary_profile_sid = _primary_customer_profile_sid(customer_info)
    if not primary_profile_sid:
        missing_fields.append("primary_customer_profile_sid or TWILIO_PRIMARY_CUSTOMER_PROFILE_SID")
    if missing_fields:
        log_step("validate_required_fields", "failed", {"missing_fields": missing_fields})
        print(f"ERROR: Missing required fields in customer_info: {', '.join(missing_fields)}")
        return {"execution_log": execution_log, "error": f"Missing required fields: {', '.join(missing_fields)}"}

    rep1_data = representative_data("rep1")
    rep2_data = representative_data("rep2") if "rep2" in customer_info else rep1_data
    validation_errors = []

    def add_validation_error(field, value, valid_values, reason="invalid value"):
        validation_errors.append({
            "field": field,
            "value": value,
            "reason": reason,
            "valid_values": valid_values,
        })

    enum_checks = [
        ("business_type", customer_info.get("business_type"), VALID_BUSINESS_TYPES),
        ("business_identity", customer_info.get("business_identity", "direct_customer"), VALID_BUSINESS_IDENTITIES),
        ("business_industry", customer_info.get("business_industry", "TECHNOLOGY"), VALID_BUSINESS_INDUSTRIES),
        (
            "business_registration_identifier",
            customer_info.get("business_registration_identifier", "EIN"),
            VALID_BUSINESS_REGISTRATION_IDENTIFIERS,
        ),
        (
            "business_regions_of_operation",
            customer_info.get("business_regions_of_operation", "USA_AND_CANADA"),
            VALID_BUSINESS_REGIONS_OF_OPERATION,
        ),
    ]
    for field, value, valid_values in enum_checks:
        if value not in valid_values:
            add_validation_error(field, value, sorted(valid_values))

    for rep_name, rep_data in (("rep1", rep1_data), ("rep2", rep2_data)):
        if rep_data.get("job_position") not in VALID_JOB_POSITIONS:
            add_validation_error(f"{rep_name}.job_position", rep_data.get("job_position"), sorted(VALID_JOB_POSITIONS))
        if not EMAIL_RE.match(rep_data.get("email", "")):
            add_validation_error(f"{rep_name}.email", rep_data.get("email"), "valid email address")
        if not E164_PHONE_RE.match(rep_data.get("phone_number", "")):
            add_validation_error(f"{rep_name}.phone_number", rep_data.get("phone_number"), "E.164 phone number, e.g. +14155551234")

    if not EMAIL_RE.match(customer_info.get("email", "")):
        add_validation_error("email", customer_info.get("email"), "valid email address")
    if "phone" in customer_info and not E164_PHONE_RE.match(customer_info.get("phone", "")):
        add_validation_error("phone", customer_info.get("phone"), "E.164 phone number, e.g. +14155551234")
    if not _valid_http_url(customer_info.get("website", "")):
        add_validation_error("website", customer_info.get("website"), "HTTP or HTTPS URL")
    if not COUNTRY_CODE_RE.match(customer_info.get("country", "")):
        add_validation_error("country", customer_info.get("country"), "two-letter ISO country code, e.g. US")
    if customer_info.get("country") == "US" and customer_info.get("region") not in US_STATE_CODES:
        add_validation_error("region", customer_info.get("region"), sorted(US_STATE_CODES), "US state or DC code")
    if not CUSTOMER_PROFILE_SID_RE.match(primary_profile_sid):
        add_validation_error("primary_customer_profile_sid", primary_profile_sid, "BU SID with 32 hex characters")

    phone_numbers_for_validation = (
        [target_phone_numbers] if isinstance(target_phone_numbers, str) else target_phone_numbers
    )
    if not isinstance(phone_numbers_for_validation, list) or not phone_numbers_for_validation:
        add_validation_error("phone_numbers", target_phone_numbers, "non-empty list of E.164 phone numbers")
    else:
        for index, phone_number in enumerate(phone_numbers_for_validation):
            if not E164_PHONE_RE.match(str(phone_number)):
                add_validation_error(
                    f"phone_numbers[{index}]",
                    phone_number,
                    "E.164 phone number, e.g. +14155551234",
                )

    if validation_errors:
        log_step("validate_required_fields", "failed", {"validation_errors": validation_errors})
        print("ERROR: Invalid customer configuration values.")
        for error in validation_errors:
            print(f"  - {error['field']}: {error['value']} ({error['reason']})")
        return {
            "execution_log": execution_log,
            "error": "Invalid customer configuration values",
            "validation_errors": validation_errors,
        }
    log_step("validate_required_fields", "success")

    try:
        # --- POLICY LOOKUPS ---
        log_step("lookup_policies", "started")
        SECONDARY_POLICY_SID, primary_profile = _secondary_policy_sid(primary_profile_sid)
        SHAKEN_POLICY_SID = _shaken_stir_policy_sid()

        if not SECONDARY_POLICY_SID:
            log_step("lookup_policies", "failed", {
                "error": "Primary Customer Profile did not return a policy SID",
                "primary_profile_sid": primary_profile_sid
            })
            print("ERROR: Primary Customer Profile did not return a policy SID.")
            return {"execution_log": execution_log, "error": "Primary Customer Profile did not return a policy SID"}
        if not SHAKEN_POLICY_SID:
            log_step("lookup_policies", "failed", {"error": "SHAKEN/STIR policy not found"})
            print("ERROR: SHAKEN/STIR policy SID not configured.")
            return {"execution_log": execution_log, "error": "SHAKEN/STIR policy not found"}

        policy_details = {
            "secondary_policy_sid": SECONDARY_POLICY_SID,
            "secondary_policy_source": "environment" if SECONDARY_POLICY_SID_ENV else "hardcoded_default",
            "primary_profile_sid": primary_profile_sid,
            "shaken_policy_sid": SHAKEN_POLICY_SID,
            "shaken_policy_source": "environment" if SHAKEN_POLICY_SID_ENV else "documented_default"
        }
        if primary_profile:
            policy_details["primary_profile_status"] = primary_profile.status

        log_step("lookup_policies", "success", policy_details)
        print(f"Using Secondary Profile Policy: {SECONDARY_POLICY_SID}")
        print(f"Using SHAKEN/STIR Policy: {SHAKEN_POLICY_SID}")

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
            existing_profile_endpoint_sids = {
                endpoint.channel_endpoint_sid
                for endpoint in client.trusthub.v1.customer_profiles(existing_profile.sid).customer_profiles_channel_endpoint_assignment.list()
            }
            existing_trust_product_endpoint_sids = {
                endpoint.channel_endpoint_sid
                for endpoint in client.trusthub.v1.trust_products(existing_trust_product.sid).trust_products_channel_endpoint_assignment.list()
            }

            for phone_number, phone_sid in phone_number_sids:
                if phone_sid in existing_profile_endpoint_sids:
                    print(f"  INFO: {phone_number} already assigned to Customer Profile")
                else:
                    try:
                        client.trusthub.v1.customer_profiles(existing_profile.sid).customer_profiles_channel_endpoint_assignment.create(
                            channel_endpoint_type="phone-number",
                            channel_endpoint_sid=phone_sid
                        )
                        print(f"  ✓ Newly assigned {phone_number} to Customer Profile")
                    except TwilioRestException as e:
                        if "already" not in str(e).lower():
                            print(f"  ✗ Failed to assign {phone_number} to Customer Profile: {e}")
                            failed_numbers.append((phone_number, str(e)))
                            continue

                if phone_sid in existing_trust_product_endpoint_sids:
                    print(f"  INFO: {phone_number} already assigned to Trust Product")
                    already_assigned.append(phone_number)
                else:
                    try:
                        client.trusthub.v1.trust_products(existing_trust_product.sid).trust_products_channel_endpoint_assignment.create(
                            channel_endpoint_type="phone-number",
                            channel_endpoint_sid=phone_sid
                        )
                        print(f"  ✓ Newly assigned {phone_number} to Trust Product")
                        assigned_numbers.append(phone_number)
                    except TwilioRestException as e:
                        if "already" in str(e).lower():
                            print(f"  INFO: {phone_number} already assigned to Trust Product")
                            already_assigned.append(phone_number)
                        else:
                            print(f"  ✗ Failed to assign {phone_number}: {e}")
                            failed_numbers.append((phone_number, str(e)))

            log_step("assign_new_phone_numbers", "success", {
                "newly_assigned": len(assigned_numbers),
                "already_assigned": len(already_assigned),
                "failed": len(failed_numbers)
            })

            if failed_numbers:
                return {
                    "execution_log": execution_log,
                    "error": "Failed to assign all phone numbers to existing resources",
                    "failed_numbers": failed_numbers
                }

            trust_product_evaluation_result = None
            if existing_trust_product.status in ("pending-review", "twilio-approved"):
                log_step("submit_existing_trust_product_for_review", "skipped", {
                    "trust_product_status": existing_trust_product.status
                })
            else:
                log_step("evaluate_existing_trust_product", "started")
                trust_product_evaluation = client.trusthub.v1.trust_products(existing_trust_product.sid).trust_products_evaluations.create(
                    policy_sid=SHAKEN_POLICY_SID
                )
                trust_product_evaluation_result = _evaluation_result(trust_product_evaluation)
                if trust_product_evaluation.status != "compliant":
                    log_step("evaluate_existing_trust_product", "failed", trust_product_evaluation_result)
                    return {
                        "execution_log": execution_log,
                        "error": "Existing Trust Product evaluation failed",
                        "evaluation": trust_product_evaluation_result
                    }
                log_step("evaluate_existing_trust_product", "success", trust_product_evaluation_result)

                log_step("submit_existing_trust_product_for_review", "started")
                client.trusthub.v1.trust_products(existing_trust_product.sid).update(status="pending-review")
                log_step("submit_existing_trust_product_for_review", "success")

            return {
                "profile_sid": existing_profile.sid,
                "trust_product_sid": existing_trust_product.sid,
                "assigned_numbers": assigned_numbers + already_assigned,
                "failed_numbers": failed_numbers,
                "total_requested": len(phone_number_sids),
                "trust_product_evaluation": trust_product_evaluation_result,
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

        # STEP 1: CREATE EMPTY SECONDARY CUSTOMER PROFILE
        # Create the bundle before dependent components so account/policy
        # restrictions fail before creating orphan Trust Hub entities.
        log_step("create_customer_profile", "started")
        profile = client.trusthub.v1.customer_profiles.create(
            friendly_name=f"Secondary Profile: {customer_info['business_name']}",
            email=customer_info['email'],
            policy_sid=SECONDARY_POLICY_SID
        )
        log_step("create_customer_profile", "success", {"profile_sid": profile.sid})

        # STEP 2: CREATE ADDRESS
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

        # STEP 3: CREATE SUPPORTING DOCUMENT
        # The Trust Hub secondary profile flow uses a customer_profile_address
        # document that links to the Address SID.
        log_step("create_address_document", "started")
        address_doc = client.trusthub.v1.supporting_documents.create(
            friendly_name=f"Address - {customer_info['business_name']}",
            type="customer_profile_address",
            attributes={"address_sids": address.sid}
        )
        log_step("create_address_document", "success", {"address_doc_sid": address_doc.sid})

        # STEP 4: CREATE END USERS (Three Required per documentation)
        # 1. Business Legal Info (Required attributes: identity, industry, regions)
        log_step("create_business_info_end_user", "started")
        biz_info = client.trusthub.v1.end_users.create(
            friendly_name="Business Legal Information",
            type="customer_profile_business_information",
            attributes={
                "business_name": customer_info['business_name'],
                "business_type": customer_info['business_type'],
                "business_registration_number": customer_info['tax_id'],
                "business_registration_identifier": customer_info.get('business_registration_identifier', 'EIN'),
                "business_identity": customer_info.get('business_identity', 'direct_customer'),
                "business_industry": customer_info.get('business_industry', 'TECHNOLOGY'),
                "business_regions_of_operation": customer_info.get('business_regions_of_operation', 'USA_AND_CANADA'),
                "website_url": customer_info['website']
            }
        )
        log_step("create_business_info_end_user", "success", {"biz_info_sid": biz_info.sid})

        # 2. Authorized Representative 1
        log_step("create_rep1_end_user", "started")
        rep1_data = representative_data("rep1")
        rep1 = client.trusthub.v1.end_users.create(
            friendly_name="Primary Authorized Representative",
            type="authorized_representative_1",
            attributes=rep1_data
        )
        log_step("create_rep1_end_user", "success", {"rep1_sid": rep1.sid})

        # 3. Authorized Representative 2 (The policy requires two distinct rep assignments)
        # If rep2 data not provided, use rep1 data (common for small businesses)
        log_step("create_rep2_end_user", "started")
        rep2_data = representative_data("rep2") if "rep2" in customer_info else rep1_data
        rep2 = client.trusthub.v1.end_users.create(
            friendly_name="Secondary Authorized Representative",
            type="authorized_representative_2",
            attributes=rep2_data
        )
        log_step("create_rep2_end_user", "success", {"rep2_sid": rep2.sid})
        print("Created End User entities (Business Info, Rep 1, and Rep 2).")

        # STEP 5: ASSIGN ALL ENTITIES TO THE PROFILE
        log_step("assign_entities_to_profile", "started")
        entities_to_assign = [primary_profile_sid, address_doc.sid, biz_info.sid, rep1.sid, rep2.sid]
        for i, sid in enumerate(entities_to_assign):
            client.trusthub.v1.customer_profiles(profile.sid).customer_profiles_entity_assignments.create(object_sid=sid)
        log_step("assign_entities_to_profile", "success", {
            "entities_assigned": len(entities_to_assign),
            "entity_sids": entities_to_assign
        })

        # STEP 6: ASSIGN ALL PHONE NUMBERS TO SECONDARY CUSTOMER PROFILE
        log_step("assign_phone_numbers_to_profile", "started", {"phone_count": len(phone_number_sids)})
        profile_assigned_numbers = []
        profile_failed_numbers = []
        for phone_number, phone_sid in phone_number_sids:
            try:
                client.trusthub.v1.customer_profiles(profile.sid).customer_profiles_channel_endpoint_assignment.create(
                    channel_endpoint_type="phone-number",
                    channel_endpoint_sid=phone_sid
                )
                print(f"  ✓ Assigned {phone_number} to Customer Profile")
                profile_assigned_numbers.append(phone_number)
            except TwilioRestException as e:
                print(f"  ✗ Failed to assign {phone_number} to Customer Profile: {e}")
                profile_failed_numbers.append((phone_number, str(e)))

        if profile_failed_numbers:
            log_step("assign_phone_numbers_to_profile", "failed", {
                "assigned_count": len(profile_assigned_numbers),
                "failed_numbers": [{"number": num, "error": err} for num, err in profile_failed_numbers]
            })
            return {
                "execution_log": execution_log,
                "error": "Failed to assign all phone numbers to Customer Profile",
                "failed_numbers": profile_failed_numbers
            }

        log_step("assign_phone_numbers_to_profile", "success", {
            "assigned_count": len(profile_assigned_numbers),
            "assigned_numbers": profile_assigned_numbers
        })

        # STEP 7: EVALUATE AND SUBMIT PROFILE FOR REVIEW
        log_step("evaluate_profile", "started")
        profile_evaluation = client.trusthub.v1.customer_profiles(profile.sid).customer_profiles_evaluations.create(
            policy_sid=SECONDARY_POLICY_SID
        )
        profile_evaluation_result = _evaluation_result(profile_evaluation)
        if profile_evaluation.status != "compliant":
            log_step("evaluate_profile", "failed", profile_evaluation_result)
            return {
                "execution_log": execution_log,
                "error": "Customer Profile evaluation failed",
                "evaluation": profile_evaluation_result
            }
        log_step("evaluate_profile", "success", profile_evaluation_result)

        log_step("submit_profile_for_review", "started")
        client.trusthub.v1.customer_profiles(profile.sid).update(status="pending-review")
        log_step("submit_profile_for_review", "success")
        print(f"Secondary Customer Profile {profile.sid} submitted for review.")

        # STEP 8: CREATE STIR/SHAKEN TRUST PRODUCT
        log_step("create_trust_product", "started")
        trust_product = client.trusthub.v1.trust_products.create(
            friendly_name=f"STIR/SHAKEN: {customer_info['business_name']}",
            email=customer_info['email'],
            policy_sid=SHAKEN_POLICY_SID
        )
        log_step("create_trust_product", "success", {"trust_product_sid": trust_product.sid})

        # STEP 9: LINK SECONDARY PROFILE TO TRUST PRODUCT
        log_step("link_profile_to_trust_product", "started")
        client.trusthub.v1.trust_products(trust_product.sid).trust_products_entity_assignments.create(object_sid=profile.sid)
        log_step("link_profile_to_trust_product", "success")

        # STEP 10: ASSIGN ALL PHONE NUMBERS TO TRUST PRODUCT (Channel Endpoints)
        log_step("assign_phone_numbers", "started", {"phone_count": len(phone_number_sids)})
        print(f"Assigning {len(phone_number_sids)} phone number(s) to Trust Product...")
        assigned_numbers = []
        failed_numbers = []

        for phone_number, phone_sid in phone_number_sids:
            try:
                client.trusthub.v1.trust_products(trust_product.sid).trust_products_channel_endpoint_assignment.create(
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

        if failed_numbers:
            return {
                "profile_sid": profile.sid,
                "trust_product_sid": trust_product.sid,
                "assigned_numbers": assigned_numbers,
                "failed_numbers": failed_numbers,
                "total_requested": len(phone_number_sids),
                "execution_log": execution_log,
                "error": "Failed to assign all phone numbers to Trust Product"
            }

        # STEP 11: EVALUATE AND SUBMIT TRUST PRODUCT FOR REVIEW
        log_step("evaluate_trust_product", "started")
        trust_product_evaluation = client.trusthub.v1.trust_products(trust_product.sid).trust_products_evaluations.create(
            policy_sid=SHAKEN_POLICY_SID
        )
        trust_product_evaluation_result = _evaluation_result(trust_product_evaluation)
        if trust_product_evaluation.status != "compliant":
            log_step("evaluate_trust_product", "failed", trust_product_evaluation_result)
            return {
                "profile_sid": profile.sid,
                "trust_product_sid": trust_product.sid,
                "assigned_numbers": assigned_numbers,
                "failed_numbers": failed_numbers,
                "total_requested": len(phone_number_sids),
                "execution_log": execution_log,
                "error": "Trust Product evaluation failed",
                "evaluation": trust_product_evaluation_result
            }
        log_step("evaluate_trust_product", "success", trust_product_evaluation_result)

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
            "profile_evaluation": profile_evaluation_result,
            "trust_product_evaluation": trust_product_evaluation_result,
            "execution_log": execution_log
        }
        log_step("onboarding_complete", "success")
        return result

    except TwilioRestException as e:
        error_details = {
            "error_type": "TwilioRestException",
            "error_message": str(e),
            "error_code": getattr(e, 'code', None),
            "error_status": getattr(e, 'status', None)
        }
        if "restricted via API for Primary Customer Profiles" in str(e):
            error_details["diagnosis"] = (
                "Twilio treated the policy SID as a Primary Customer Profile policy. "
                "Confirm the parent Primary Customer Profile is configured as ISV/Reseller, "
                "or set TWILIO_SECONDARY_CUSTOMER_PROFILE_POLICY_SID to a Secondary Customer Profile policy SID."
            )
        log_step("onboarding_failed", "error", error_details)
        print(f"\nTwilio API Error: {e}")
        if "diagnosis" in error_details:
            print(f"Diagnosis: {error_details['diagnosis']}")
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
        "primary_customer_profile_sid": "BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",

        # Optional fields (with defaults shown)
        "business_industry": "TECHNOLOGY",  # Default: TECHNOLOGY
        "business_regions_of_operation": "USA_AND_CANADA",  # Default: USA_AND_CANADA
        "job_position": "Director",  # Default: Director
        "business_title": "Director",  # Default: job_position

        # Optional: Separate representative data (if different from primary contact)
        # "rep1": {
        #     "first_name": "John",
        #     "last_name": "Doe",
        #     "email": "john@acme.example",
        #     "phone_number": "+14155551234",
        #     "business_title": "CEO",
        #     "job_position": "CEO"
        # },
        # "rep2": {
        #     "first_name": "Jane",
        #     "last_name": "Smith",
        #     "email": "jane@acme.example",
        #     "phone_number": "+14155551235",
        #     "business_title": "CFO",
        #     "job_position": "CFO"
        # }
    }
    # Multiple phone numbers
    PHONES_TO_REGISTER = [
        "+14155556789",
        "+14155556790",
        "+14155556791"
    ]

    result = onboard_isv_customer(data, PHONES_TO_REGISTER)

    if result and "profile_sid" in result:
        print(f"\nSuccess! Profile SID: {result['profile_sid']}")
        print(f"Assigned {result['assigned_numbers']} number(s)")
    elif result:
        print(f"\nOnboarding failed: {result.get('error', 'Unknown error')}")
