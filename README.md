# **Twilio Trust Hub Customer Onboarding**

This script automates the registration of Secondary Business Profiles and STIR/SHAKEN Trust Products for ISV customers. It handles the Trust Hub resource hierarchy, including dynamic policy discovery, primary-to-secondary profile linking, phone number assignments, and pre-submission evaluations.

## **Workflow Overview**

The script follows Twilio's "bottom-up" registration requirement:

1. **Address Creation**: Establishes the physical location of the business.
2. **Supporting Document**: Links the Address SID with a Trust Hub `customer_profile_address` supporting document.
3. **End User Entities**: Creates the required three legal entities (Business Info, Rep 1, and Rep 2).
4. **Customer Profile**: Bundles the entities into a Secondary Business Profile and links the approved Primary Business Profile.
5. **Trust Product**: Creates the SHAKEN/STIR registration linked to the profile.
6. **Channel Assignment**: Links phone number(s) to both the Secondary Business Profile and Trust Product.
7. **Evaluation and Review**: Evaluates both Trust Hub resources before moving them to `pending-review`.

## **Files in this Repository**

- `main.py` - Core onboarding script with the `onboard_isv_customer()` function
- `batch_onboard.py` - Process multiple customers from a JSON file
- `check_status.py` - Check the approval status of submitted profiles
- `customers_example.json` - Example configuration for batch processing

## **Requirements**

* **Python 3.8+** (tested with 3.12)
* **twilio-python v9.10.2+**
* **Approved Primary Business Profile**: Your main ISV account must already have an approved profile.

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
export TWILIO_PRIMARY_CUSTOMER_PROFILE_SID='BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
# Optional overrides:
export TWILIO_SECONDARY_CUSTOMER_PROFILE_POLICY_SID='RNxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
export TWILIO_SHAKEN_STIR_POLICY_SID='RNxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
```

The script validates Twilio credentials before making any API calls. The primary customer profile SID can be supplied through `TWILIO_PRIMARY_CUSTOMER_PROFILE_SID` or as `primary_customer_profile_sid` in each customer object. By default, the script uses the hardcoded Secondary Customer Profile policy SID `RNdfbf3fae0e1107f8aded0e7cead80bf5`. The `TWILIO_SECONDARY_CUSTOMER_PROFILE_POLICY_SID` environment variable can override that value when needed. The SHAKEN/STIR policy defaults to Twilio's documented policy SID unless `TWILIO_SHAKEN_STIR_POLICY_SID` is set.

## **Configuration Options**

### **Required Fields**
- `business_name`, `street`, `city`, `region`, `postal_code`, `country`
- `business_type`, `tax_id`, `website`
- `first_name`, `last_name`, `email`, `phone`
- `primary_customer_profile_sid` unless `TWILIO_PRIMARY_CUSTOMER_PROFILE_SID` is set

### **Optional Fields (with defaults)**
- `business_industry`: Default `"TECHNOLOGY"`
- `business_regions_of_operation`: Default `"USA_AND_CANADA"`
  - Valid values: `USA_AND_CANADA`, `EUROPE`, `AFRICA`, `ASIA`, `AUSTRALIA`, `LATIN_AMERICA`
- `job_position`: Default `"Director"`
- `business_title`: Defaults to `job_position`

### **Representative Data**

Both representative formats are supported:

- Simple format: provide top-level `first_name`, `last_name`, `phone`, `business_title`, and `job_position`. The script uses that contact for `rep1` and reuses it for `rep2`.
- Explicit format: provide `rep1` and optionally `rep2` objects. If `rep2` is omitted, the script reuses `rep1`.

When using explicit representative objects, each representative needs `first_name`, `last_name`, `email`, and `phone_number`. `business_title` and `job_position` are optional and default from the top-level fields when present.

```python
customer_data = {
    # ... business fields ...
    "email": "compliance@example.com",
    "rep1": {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone_number": "+14085551234",
        "business_title": "CEO",
        "job_position": "CEO"
    },
    "rep2": {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane@example.com",
        "phone_number": "+14085551235",
        "business_title": "CFO",
        "job_position": "CFO"
    }
}
```

Do not leave placeholder representative values from the example in a real customer file; Twilio will evaluate the values submitted in `rep1` and `rep2`.

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
    "primary_customer_profile_sid": "BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    # Optional fields (will use defaults if not provided):
    "business_industry": "TECHNOLOGY",  # See Twilio docs for valid values
    "business_regions_of_operation": "USA_AND_CANADA"  # Can be USA_AND_CANADA, EUROPE, etc.
}

onboard_isv_customer(
    customer_info=customer_data,
    target_phone_numbers="+14085556789"  # Single number as string
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
    target_phone_numbers=phone_numbers  # List of numbers
)
```

The script will:
1. Validate all phone numbers exist in your account before proceeding
2. Create a single Customer Profile and Trust Product
3. Assign each phone number to the Secondary Customer Profile and Trust Product
4. Evaluate each resource before submission
5. Report success/failure for each phone number assignment

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
python check_status.py BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The script will show the current status, creation dates, and assigned entities/phone numbers.

## **Technical Implementation Details**

### **Policy Resolution**

The script first checks `TWILIO_SECONDARY_CUSTOMER_PROFILE_POLICY_SID`. If it is missing, it uses the hardcoded Secondary Customer Profile policy SID `RNdfbf3fae0e1107f8aded0e7cead80bf5`. The configured Primary Customer Profile is still fetched so the script can validate access and log its approval status before creating the Secondary Customer Profile.

The SHAKEN/STIR Trust Product uses `TWILIO_SHAKEN_STIR_POLICY_SID` when set, otherwise it uses Twilio's documented SHAKEN/STIR policy SID. This avoids brittle friendly-name policy lookups.

### **Multiple Phone Number Support**

When registering multiple phone numbers:
- All phone numbers are validated upfront before any resources are created
- Invalid/missing numbers are skipped with a warning
- Each phone number is assigned to the Secondary Customer Profile and Trust Product in a loop with individual error handling
- Failed assignments are logged and returned as an error before submission

### **Return Value**

The function returns a dictionary with created resource information:

```python
{
    "profile_sid": "BU...",              # Customer Profile SID
    "trust_product_sid": "BU...",        # Trust Product SID
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
The Secondary Customer Profile is also linked to the approved Primary Customer Profile by assigning the Primary Customer Profile SID to the Secondary Customer Profile.

### **Vetting Status**

Verification is an asynchronous process. The script creates a Trust Hub evaluation for both the Customer Profile and the SHAKEN/STIR Trust Product, then only moves the resource to `pending-review` if the evaluation returns `compliant`. Review typically takes 24 to 72 hours.

## **Errors and Troubleshooting**

* **Missing Credentials**: If you see "Missing Twilio credentials", ensure `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` environment variables are set.
* **Missing Required Fields**: The script validates required fields before making API calls. If you see "Missing required fields", ensure your `customer_info` dictionary includes all required fields listed in the Configuration section.
* **Primary Profile Policy Missing**: If you see "Primary Customer Profile did not return a policy SID", verify the `primary_customer_profile_sid` value is a valid Trust Hub Customer Profile SID in the account used by your credentials.
* **Primary Customer Profiles Restricted via API**: If Twilio says "This operation is restricted via API for Primary Customer Profiles. Use Twilio Console instead.", the policy SID is being treated as a Primary Customer Profile policy. Confirm the parent Primary Customer Profile is configured as ISV/Reseller, or set `TWILIO_SECONDARY_CUSTOMER_PROFILE_POLICY_SID` to the correct Secondary Customer Profile policy SID.
* **Phone Number Not Found**: Ensure phone numbers are formatted in E.164 format (e.g., `+14155551234`) and exist in your Twilio account before running the script. The script validates all numbers upfront.
* **Incomplete Entities**: If the script fails at the submission step, ensure all required attributes (Business Industry, Regions of Operation, etc.) are valid enums. Valid values for `business_regions_of_operation` include: `USA_AND_CANADA`, `EUROPE`, `AFRICA`, `ASIA`, `AUSTRALIA`, `LATIN_AMERICA`.
* **Duplicate Submissions**: Twilio may reject profiles that use identical data to an existing submission.
* **Partial Phone Number Assignment**: If some phone numbers fail to assign, check individual error messages in the summary. Common causes include numbers already assigned to another Trust Product or incorrect number ownership. The script stops before submission if all phone number assignments are not clean.
