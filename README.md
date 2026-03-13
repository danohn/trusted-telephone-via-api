# **Twilio Trust Hub Customer Onboarding**

This script automates the registration of Secondary Business Profiles and STIR/SHAKEN Trust Products for ISV customers. It handles the full resource hierarchy required by Twilio Trust Hub, including physical file uploads for business verification and dynamic policy discovery across multiple Twilio accounts.

## **Workflow Overview**

The script follows Twilio's "bottom-up" registration requirement:

1. **Address Creation**: Establishes the physical location of the business.
2. **Supporting Documents**: Links the Address SID and uploads a physical file (Business License/EIN).
3. **End User Entities**: Creates the required three legal entities (Business Info, Rep 1, and Rep 2).
4. **Customer Profile**: Bundles the entities into a Secondary Business Profile.
5. **Trust Product**: Creates the SHAKEN/STIR registration linked to the profile.
6. **Channel Assignment**: Links phone number(s) to the product for A-level attestation (supports single or multiple numbers).

## **Files in this Repository**

- `main.py` - Core onboarding script with the `onboard_isv_customer()` function
- `batch_onboard.py` - Process multiple customers from a JSON file
- `check_status.py` - Check the approval status of submitted profiles
- `customers_example.json` - Example configuration for batch processing

## **Requirements**

* **Python 3.8+** (tested with 3.12)
* **twilio-python v9.10.2+**
* **Approved Primary Business Profile**: Your main ISV account must already have an approved profile.
* **Local Document**: A valid PDF, JPEG, or PNG of the customer's business registration (max 5MB).

## **Installation**

Install the required helper library:

Bash

```
pip install twilio
```

Or use uv (faster):

```
uv pip install twilio
```

## **Environment Variables**

Set your credentials in your environment to avoid hardcoding them into the script:

Bash

```
export TWILIO_ACCOUNT_SID='ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
export TWILIO_AUTH_TOKEN='your_auth_token'
```

The script will validate these are set before making any API calls.

## **Configuration Options**

### **Required Fields**
- `business_name`, `street`, `city`, `region`, `postal_code`, `country`
- `business_type`, `tax_id`, `website`
- `first_name`, `last_name`, `email`, `phone`

### **Optional Fields (with defaults)**
- `business_industry`: Default `"TECHNOLOGY"`
- `business_regions_of_operation`: Default `"USA_AND_CANADA"`
  - Valid values: `USA_AND_CANADA`, `EUROPE`, `AFRICA`, `ASIA`, `AUSTRALIA`, `SOUTH_AMERICA`, `CENTRAL_AMERICA`
- `job_position`: Default `"Director"`

### **Advanced: Separate Representative Data**

If your customer has different authorized representatives, you can specify them separately:

```python
customer_data = {
    # ... basic fields ...
    "rep1": {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone_number": "+14085551234",
        "job_position": "CEO"
    },
    "rep2": {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane@example.com",
        "phone_number": "+14085551235",
        "job_position": "CFO"
    }
}
```

If not provided, both representatives will use the primary contact information.

## **Usage**

The script performs dynamic lookups, meaning it will query the account for the specific Policy SIDs (Secondary Profile and SHAKEN) and the Phone Number SIDs automatically.

### **Single Phone Number**

Python

```
from main import onboard_isv_customer

customer_data = {
    "business_name": "Example Corp",
    "street": "101 Enterprise Way",
    "city": "San Jose",
    "region": "CA",
    "postal_code": "95110",
    "country": "US",
    "business_type": "Corporation",
    "tax_id": "12-3456789",
    "website": "https://example.com",
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "compliance@example.com",
    "phone": "+14085551234",
    # Optional fields (will use defaults if not provided):
    "business_industry": "TECHNOLOGY",  # See Twilio docs for valid values
    "business_regions_of_operation": "USA_AND_CANADA"  # Can be USA_AND_CANADA, EUROPE, etc.
}

onboard_isv_customer(
    customer_info=customer_data,
    target_phone_numbers="+14085556789",  # Single number as string
    file_path="documents/business_license.pdf"
)
```

### **Multiple Phone Numbers**

For customers with many phone numbers (e.g., 52 numbers), pass a list:

Python

```
from main import onboard_isv_customer

customer_data = {
    # ... same as above ...
}

# List of phone numbers to register
phone_numbers = [
    "+14085556789",
    "+14085556790",
    "+14085556791",
    # ... up to 52 or more numbers
]

onboard_isv_customer(
    customer_info=customer_data,
    target_phone_numbers=phone_numbers,  # List of numbers
    file_path="documents/business_license.pdf"
)
```

The script will:
1. Validate all phone numbers exist in your account before proceeding
2. Create a single Customer Profile and Trust Product
3. Loop through and assign each phone number to the Trust Product
4. Report success/failure for each phone number assignment

### **Batch Processing Multiple Customers**

For processing multiple customers at once, use the batch script:

```bash
python batch_onboard.py customers.json
```

See `customers_example.json` for the expected format. The batch script:
- Processes customers sequentially with rate limiting
- Saves results to a JSON file
- Provides detailed summary of successes/failures

### **Checking Status**

After submission, check the approval status of your profiles:

```bash
# Check Customer Profile status
python check_status.py BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Check Trust Product status
python check_status.py BTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The script will show the current status, creation dates, and assigned entities/phone numbers.

## **Technical Implementation Details**

### **Policy Discovery**

The script uses `client.trusthub.v1.policies.list()` to locate the correct Policy SIDs. This ensures compatibility across different Twilio projects where SID values may differ, provided the `friendly_name` matches "Secondary Customer Profile of type Business" and "SHAKEN/STIR".

The script now validates that both required policies exist before proceeding, providing specific error messages if either is missing.

### **Multiple Phone Number Support**

When registering multiple phone numbers:
- All phone numbers are validated upfront before any resources are created
- Invalid/missing numbers are skipped with a warning
- Each phone number is assigned to the Trust Product in a loop with individual error handling
- Failed assignments are logged but don't block the overall process

### **Return Value**

The function returns a dictionary with created resource information:

```python
{
    "profile_sid": "BU...",              # Customer Profile SID
    "trust_product_sid": "BT...",        # Trust Product SID
    "assigned_numbers": ["+1..."],       # Successfully assigned phone numbers
    "failed_numbers": [                  # Failed assignments with error messages
        ("+1...", "error message")
    ],
    "total_requested": 52                # Total phone numbers requested
}
```

Returns `None` if the operation fails before creating resources.

### **Resource Linking**

Assignments are handled via `EntityAssignments`. A profile is not considered complete until the End Users and Supporting Documents are explicitly assigned to the `CustomerProfileSid`.

### **Vetting Status**

Verification is an asynchronous process. Both the Customer Profile and the SHAKEN/STIR Trust Product are moved to `pending-review` status in the final step of their respective cycles. Review typically takes 24 to 72 hours.

## **Errors and Troubleshooting**

* **Missing Credentials**: If you see "Missing Twilio credentials", ensure `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` environment variables are set.
* **Missing Required Fields**: The script validates required fields before making API calls. If you see "Missing required fields", ensure your `customer_info` dictionary includes all required fields listed in the Configuration section.
* **Policy Not Found**: If you see "Could not find 'Secondary Customer Profile of type Business' policy" or similar, ensure your Twilio account has Trust Hub enabled and the policies are available. Check the exact friendly names in your account.
* **Phone Number Not Found**: Ensure phone numbers are formatted in E.164 format (e.g., `+14155551234`) and exist in your Twilio account before running the script. The script validates all numbers upfront.
* **File Not Found**: The script checks if the document file exists before processing. Ensure the path is correct and the file is readable.
* **Incomplete Entities**: If the script fails at the submission step, ensure all required attributes (Business Industry, Regions of Operation, etc.) are valid enums. Valid values for `business_regions_of_operation` include: `USA_AND_CANADA`, `EUROPE`, `AFRICA`, `ASIA`, `AUSTRALIA`, `SOUTH_AMERICA`, `CENTRAL_AMERICA`.
* **Duplicate Submissions**: Twilio may reject profiles that use identical data to an existing submission.
* **Partial Phone Number Assignment**: If some phone numbers fail to assign, check individual error messages in the summary. Common causes include numbers already assigned to another Trust Product or incorrect number ownership. The script continues processing remaining numbers even if some fail.