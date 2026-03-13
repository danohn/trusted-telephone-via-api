"""
Batch onboarding script for multiple customers.

Usage:
    python batch_onboard.py customers.json

Where customers.json contains an array of customer configurations.
"""

import json
import sys
import time
from main import onboard_isv_customer


def batch_onboard(customers_file):
    """
    Process multiple customers from a JSON file.

    Expected JSON format:
    [
        {
            "customer_info": { ... },
            "phone_numbers": ["+1...", "+1..."],
            "document_path": "path/to/doc.pdf"
        },
        ...
    ]
    """
    try:
        with open(customers_file, 'r') as f:
            customers = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: File not found: {customers_file}")
        return
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {customers_file}: {e}")
        return

    total = len(customers)
    successful = 0
    failed = 0
    results = []

    print(f"Starting batch onboarding for {total} customer(s)...\n")

    for i, customer in enumerate(customers, 1):
        business_name = customer.get('customer_info', {}).get('business_name', 'Unknown')
        print(f"\n{'='*60}")
        print(f"Processing {i}/{total}: {business_name}")
        print(f"{'='*60}")

        try:
            result = onboard_isv_customer(
                customer_info=customer['customer_info'],
                target_phone_numbers=customer['phone_numbers'],
                file_path=customer['document_path']
            )

            if result:
                successful += 1
                results.append({
                    "business_name": business_name,
                    "status": "success",
                    "profile_sid": result['profile_sid'],
                    "trust_product_sid": result['trust_product_sid'],
                    "assigned_numbers": len(result['assigned_numbers']),
                    "failed_numbers": len(result['failed_numbers'])
                })
            else:
                failed += 1
                results.append({
                    "business_name": business_name,
                    "status": "failed",
                    "error": "Onboarding returned None"
                })

        except Exception as e:
            failed += 1
            results.append({
                "business_name": business_name,
                "status": "failed",
                "error": str(e)
            })
            print(f"ERROR processing {business_name}: {e}")

        # Rate limiting - wait between customers to avoid API throttling
        if i < total:
            print("\nWaiting 2 seconds before next customer...")
            time.sleep(2)

    # Final summary
    print(f"\n\n{'='*60}")
    print("BATCH ONBOARDING SUMMARY")
    print(f"{'='*60}")
    print(f"Total Customers: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nDetailed Results:")

    for result in results:
        print(f"\n{result['business_name']}: {result['status'].upper()}")
        if result['status'] == 'success':
            print(f"  Profile SID: {result['profile_sid']}")
            print(f"  Trust Product SID: {result['trust_product_sid']}")
            print(f"  Numbers Assigned: {result['assigned_numbers']}")
            if result['failed_numbers'] > 0:
                print(f"  Numbers Failed: {result['failed_numbers']}")
        else:
            print(f"  Error: {result.get('error', 'Unknown')}")

    # Save results to file
    output_file = customers_file.replace('.json', '_results.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python batch_onboard.py customers.json")
        sys.exit(1)

    batch_onboard(sys.argv[1])
