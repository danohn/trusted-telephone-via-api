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
            "phone_numbers": ["+1...", "+1..."]
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
                target_phone_numbers=customer['phone_numbers']
            )

            if result and 'profile_sid' in result:
                successful += 1
                results.append({
                    "business_name": business_name,
                    "status": "success",
                    "profile_sid": result['profile_sid'],
                    "trust_product_sid": result['trust_product_sid'],
                    "assigned_numbers": len(result['assigned_numbers']),
                    "failed_numbers": len(result['failed_numbers']),
                    "reused_existing": result.get('reused_existing', False),
                    "execution_log": result.get('execution_log', [])
                })
            elif result and 'error' in result:
                failed += 1
                results.append({
                    "business_name": business_name,
                    "status": "failed",
                    "error": result.get('error', 'Unknown error'),
                    "error_type": result.get('error_type', 'Unknown'),
                    "execution_log": result.get('execution_log', [])
                })
            else:
                failed += 1
                results.append({
                    "business_name": business_name,
                    "status": "failed",
                    "error": "Onboarding returned unexpected result",
                    "result": str(result)
                })

        except Exception as e:
            failed += 1
            import traceback
            results.append({
                "business_name": business_name,
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
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
            if result.get('reused_existing'):
                print(f"  [REUSED] Existing resources")
            else:
                print(f"  [CREATED] New resources")
            print(f"  Profile SID: {result['profile_sid']}")
            print(f"  Trust Product SID: {result['trust_product_sid']}")
            print(f"  Numbers Assigned: {result['assigned_numbers']}")
            if result['failed_numbers'] > 0:
                print(f"  Numbers Failed: {result['failed_numbers']}")
        else:
            print(f"  Error Type: {result.get('error_type', 'Unknown')}")
            print(f"  Error: {result.get('error', 'Unknown')}")

            # Print execution log for failed cases to show where it stopped
            if 'execution_log' in result and result['execution_log']:
                print(f"  Last successful step: ", end="")
                success_steps = [log for log in result['execution_log'] if log['status'] == 'success']
                if success_steps:
                    print(success_steps[-1]['step'])
                else:
                    print("None")

                failed_steps = [log for log in result['execution_log'] if log['status'] in ('failed', 'error')]
                if failed_steps:
                    print(f"  Failed at step: {failed_steps[0]['step']}")
                    if 'details' in failed_steps[0]:
                        print(f"  Failure details: {failed_steps[0]['details']}")

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
