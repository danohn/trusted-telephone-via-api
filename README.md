# **Twilio Trust Hub Customer Onboarding**

This script automates the registration of Secondary Business Profiles and STIR/SHAKEN Trust Products for ISV customers. It handles the full resource hierarchy required by Twilio Trust Hub, including physical file uploads for business verification and dynamic policy discovery across multiple Twilio accounts.

## **Workflow Overview**

The script follows Twilio's "bottom-up" registration requirement:

1. **Address Creation**: Establishes the physical location of the business.  
2. **Supporting Documents**: Links the Address SID and uploads a physical file (Business License/EIN).  
3. **End User Entities**: Creates the required three legal entities (Business Info, Rep 1, and Rep 2).  
4. **Customer Profile**: Bundles the entities into a Secondary Business Profile.  
5. **Trust Product**: Creates the SHAKEN/STIR registration linked to the profile.  
6. **Channel Assignment**: Links a specific phone number to the product for A-level attestation.

## **Requirements**

* **Python 3.8+**  
* **twilio-python v9.10.2+**  
* **Approved Primary Business Profile**: Your main ISV account must already have an approved profile.  
* **Local Document**: A valid PDF, JPEG, or PNG of the customer's business registration (max 5MB).

## **Installation**

Install the required helper library:

Bash

```
pip install twilio
```

## **Environment Variables**

Set your credentials in your environment to avoid hardcoding them into the script:

Bash

```
export TWILIO_ACCOUNT_SID='ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
export TWILIO_AUTH_TOKEN='your_auth_token'
```

## **Usage**

The script performs dynamic lookups, meaning it will query the account for the specific Policy SIDs (Secondary Profile and SHAKEN) and the Phone Number SID automatically.

Python

```
from onboarding_script import onboard_isv_customer

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
    "phone": "+14085551234"
}

onboard_isv_customer(
    customer_info=customer_data,
    target_phone_number="+14085556789",
    file_path="documents/business_license.pdf"
)
```

## **Technical Implementation Details**

### **Policy Discovery**

The script uses `client.trusthub.v1.policies.list()` to locate the correct Policy SIDs. This ensures compatibility across different Twilio projects where SID values may differ, provided the `friendly_name` matches "Secondary Customer Profile of type Business" and "SHAKEN/STIR".

### **Resource Linking**

Assignments are handled via `EntityAssignments`. A profile is not considered complete until the End Users and Supporting Documents are explicitly assigned to the `CustomerProfileSid`.

### **Vetting Status**

Verification is an asynchronous process. Both the Customer Profile and the SHAKEN/STIR Trust Product are moved to `pending-review` status in the final step of their respective cycles. Review typically takes 24 to 72 hours.

## **Errors and Troubleshooting**

* **Incomplete Entities**: If the script fails at the submission step, ensure all required attributes (Business Industry, Regions of Operation, etc.) are valid enums.  
* **File Uploads**: Files must be binary-readable. Ensure the path to the PDF/image is absolute or correctly relative to the execution context.  
* **Duplicate Submissions**: Twilio may reject profiles that use identical data to an existing submission.