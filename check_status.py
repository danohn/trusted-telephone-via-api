"""
Check the status of Customer Profiles and Trust Products.

Usage:
    python check_status.py BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    python check_status.py BTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""

import os
import sys
from twilio.rest import Client

# Setup credentials
ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')

if not ACCOUNT_SID or not AUTH_TOKEN:
    print("ERROR: Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN environment variables.")
    sys.exit(1)

client = Client(ACCOUNT_SID, AUTH_TOKEN)


def check_customer_profile(profile_sid):
    """Check the status of a Customer Profile."""
    try:
        profile = client.trusthub.v1.customer_profiles(profile_sid).fetch()

        print(f"\n{'='*60}")
        print("CUSTOMER PROFILE STATUS")
        print(f"{'='*60}")
        print(f"SID: {profile.sid}")
        print(f"Friendly Name: {profile.friendly_name}")
        print(f"Status: {profile.status}")
        print(f"Email: {profile.email}")
        print(f"Policy SID: {profile.policy_sid}")
        print(f"Created: {profile.date_created}")
        print(f"Updated: {profile.date_updated}")

        if profile.status == "twilio-approved":
            print("\n✓ Profile is APPROVED and ready to use!")
        elif profile.status == "pending-review":
            print("\n⏳ Profile is pending review. This typically takes 24-72 hours.")
        elif profile.status == "draft":
            print("\n⚠️  Profile is still in draft status. It needs to be submitted.")
        else:
            print(f"\n⚠️  Profile status: {profile.status}")

        # List assigned entities
        print(f"\nAssigned Entities:")
        assignments = client.trusthub.v1.customer_profiles(profile_sid).customer_profiles_entity_assignments.list()
        for assignment in assignments:
            print(f"  - {assignment.object_sid}")

        return profile

    except Exception as e:
        print(f"ERROR fetching Customer Profile: {e}")
        return None


def check_trust_product(trust_product_sid):
    """Check the status of a Trust Product."""
    try:
        product = client.trusthub.v1.trust_products(trust_product_sid).fetch()

        print(f"\n{'='*60}")
        print("TRUST PRODUCT STATUS")
        print(f"{'='*60}")
        print(f"SID: {product.sid}")
        print(f"Friendly Name: {product.friendly_name}")
        print(f"Status: {product.status}")
        print(f"Email: {product.email}")
        print(f"Policy SID: {product.policy_sid}")
        print(f"Created: {product.date_created}")
        print(f"Updated: {product.date_updated}")

        if product.status == "twilio-approved":
            print("\n✓ Trust Product is APPROVED!")
        elif product.status == "pending-review":
            print("\n⏳ Trust Product is pending review. This typically takes 24-72 hours.")
        elif product.status == "draft":
            print("\n⚠️  Trust Product is still in draft status. It needs to be submitted.")
        else:
            print(f"\n⚠️  Trust Product status: {product.status}")

        # List assigned phone numbers
        print(f"\nAssigned Phone Numbers:")
        try:
            endpoints = client.trusthub.v1.trust_products(trust_product_sid).customer_profiles_channel_endpoint_assignment.list()
            for endpoint in endpoints:
                print(f"  - {endpoint.channel_endpoint_sid}")
        except Exception as e:
            print(f"  Could not fetch endpoints: {e}")

        return product

    except Exception as e:
        print(f"ERROR fetching Trust Product: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python check_status.py <PROFILE_SID or TRUST_PRODUCT_SID>")
        print("\nExamples:")
        print("  python check_status.py BUxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        print("  python check_status.py BTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        sys.exit(1)

    sid = sys.argv[1]

    if sid.startswith('BU'):
        check_customer_profile(sid)
    elif sid.startswith('BT'):
        check_trust_product(sid)
    else:
        print("ERROR: SID must start with 'BU' (Customer Profile) or 'BT' (Trust Product)")
        sys.exit(1)
