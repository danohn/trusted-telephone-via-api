# Detailed Logging and Idempotency Implementation

## Overview
Added comprehensive step-by-step logging to the onboarding process to help diagnose failures. Each step now logs its status (started/success/failed/error) with detailed information.

Also implemented idempotency - the script now checks for existing resources and reuses them instead of creating duplicates. This allows safe re-runs without creating duplicate profiles or trust products.

## Changes Made

### main.py
1. **Added `log_step()` function**: Logs each step with timestamp, status, and optional details
2. **Added `execution_log` array**: Collects all log entries throughout the execution
3. **Modified return values**: All return paths now include `execution_log` in the response

### Logged Steps (in order):
1. `validate_required_fields` - Check for missing customer info fields
2. `lookup_policies` - Find Secondary Customer Profile and SHAKEN/STIR policies
3. `check_existing_resources` - **NEW**: Search for existing profiles and trust products
4. `lookup_phone_numbers` - Resolve phone numbers to their SIDs

**If existing resources are found, the script will:**
- Reuse the existing Customer Profile and Trust Product
- Only assign phone numbers that aren't already assigned
- Skip all resource creation steps
- Return with `"reused_existing": true` in the result

**If no existing resources are found, the script continues with:**
6. `create_address` - Create Twilio address resource
7. `create_address_document` - Create address proof supporting document
8. `create_business_info_end_user` - Create business information end user
9. `create_rep1_end_user` - Create primary representative end user
10. `create_rep2_end_user` - Create secondary representative end user
11. `create_customer_profile` - Create secondary customer profile
12. `assign_entities_to_profile` - Link primary profile, address document, and end users to the profile
13. `assign_phone_numbers_to_profile` - Assign phone numbers to the secondary customer profile
14. `evaluate_profile` - Evaluate the customer profile before submission
15. `submit_profile_for_review` - Submit profile to Twilio for review
16. `create_trust_product` - Create STIR/SHAKEN trust product
17. `link_profile_to_trust_product` - Link profile to trust product
18. `assign_phone_numbers` - Assign phone numbers to trust product
19. `evaluate_trust_product` - Evaluate the trust product before submission
20. `submit_trust_product_for_review` - Submit trust product for review
21. `onboarding_complete` - Final success marker

### batch_onboard.py
1. **Enhanced result handling**: Now properly captures and saves execution_log from each customer
2. **Added error type tracking**: Captures both error message and error type
3. **Added traceback capture**: Full stack trace for unexpected exceptions
4. **Enhanced summary output**: Shows last successful step and failure point for failed customers

## Output Format

### Success Case
```json
{
  "business_name": "Example Corp",
  "status": "success",
  "profile_sid": "BU...",
  "trust_product_sid": "BU...",
  "assigned_numbers": 21,
  "failed_numbers": 0,
  "execution_log": [
    {
      "step": "validate_required_fields",
      "status": "success",
      "timestamp": "2026-05-12T12:00:00.000000"
    },
    ...
  ]
}
```

### Failure Case
```json
{
  "business_name": "Example Corp",
  "status": "failed",
  "error": "No valid phone numbers found in account",
  "error_type": "ValidationError",
  "execution_log": [
    {
      "step": "validate_required_fields",
      "status": "success",
      "timestamp": "2026-05-12T12:00:00.000000"
    },
    {
      "step": "lookup_phone_numbers",
      "status": "started",
      "timestamp": "2026-05-12T12:00:01.000000",
      "details": {"phone_count": 21}
    },
    {
      "step": "lookup_phone_numbers",
      "status": "failed",
      "timestamp": "2026-05-12T12:00:02.000000",
      "details": {
        "error": "No valid phone numbers found",
        "not_found": ["+13343250000", "+12059743700", ...]
      }
    }
  ]
}
```

## Debugging with Logs

To identify the exact point of failure:

1. Look at the `execution_log` array in the `*_results.json` file
2. Find the last step with `"status": "success"`
3. The next step (if present) will show `"status": "failed"` or `"status": "error"` with details
4. Check the `details` field for specific error information

### Common Failure Points

- **lookup_phone_numbers**: Phone numbers don't exist in the Twilio account
- **lookup_policies**: Trust Hub policies not found and policy SID environment variables are not set
- **create_address_document**: Invalid address_sids format
- **evaluate_profile**: Missing primary profile assignment, phone assignment, or invalid profile data
- **evaluate_trust_product**: Missing secondary profile assignment, phone assignment, or invalid trust product data
- **submit_profile_for_review**: Missing required entities or invalid data
- **assign_phone_numbers**: Phone numbers already assigned to another trust product

## Idempotency

The script is now **idempotent** - you can safely run it multiple times with the same customer data.

### How it works:

1. **Searches for existing resources**: Before creating anything, the script searches for existing Customer Profiles and Trust Products that match the business name
2. **Reuses existing resources**: If both are found, it reuses them instead of creating duplicates
3. **Only assigns new phone numbers**: Phone numbers already assigned to the trust product are skipped
4. **Safe error handling**: If a phone number is already assigned to *any* trust product, it's noted but doesn't cause the entire process to fail

### Example scenarios:

**First run**: Creates all resources
```json
{
  "status": "success",
  "reused_existing": false,
  "assigned_numbers": 21
}
```

**Second run (same customer)**: Reuses resources, phone numbers already assigned
```json
{
  "status": "success",
  "reused_existing": true,
  "assigned_numbers": 21,
  "execution_log": [
    ...
    {
      "step": "check_existing_resources",
      "status": "info",
      "details": {
        "found_existing_profile": true,
        "profile_sid": "BU...",
        "found_existing_trust_product": true,
        "trust_product_sid": "BU..."
      }
    }
  ]
}
```

**Partial failure recovery**: If the first run created the profile but failed before creating the trust product, the next run will create only what's missing.

## Next Run

When you run the script again with `python batch_onboard.py SolidLegal.json`, it will:
1. Generate a new `SolidLegal_results.json` with the complete execution log
2. Show exactly where the process failed (if it fails)
3. Reuse any existing resources instead of creating duplicates
4. Be safe to run multiple times without side effects
