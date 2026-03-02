import requests
import json
import sys

BASE_URL = "http://127.0.0.1:5001"

def test_pricing_cap():
    print("--- Testing Hourly Pricing Cap ---")
    
    # Needs a category id. Looking at init_db, default is 'cat-aluminio', price_full_day=15000, price_per_hour=3000
    # 6 hours = 18000, which is > 15000. So it should be capped at 15000.
    payload = {
        "items": [{"category_id": "cat-aluminio", "quantity": 1}],
        "rental_type": "hours",
        "hours": 6,
        "payment_method": "cash"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/calculate-price", json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"Subtotal: {data['subtotal']}")
        print(f"Breakdown: {data['breakdown']}")
        
        if data['subtotal'] == 15000:
            print("✅ Pricing cap works! (Capped at 15000 instead of 18000)")
        else:
            print(f"❌ Pricing cap failed! Expected 15000, got {data['subtotal']}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Connection failed: {e}. Is the server running?")
        sys.exit(1)

def test_admin_reservation():
    print("\n--- Testing Admin Reservation ---")
    session = requests.Session()
    
    # 1. Login
    login_payload = {"username": "admin", "password": "bicisi2024"} # Default password hash is used
    try:
        print("Logging in...")
        login_resp = session.post(f"{BASE_URL}/admin/login", json=login_payload)
        
        if login_resp.status_code == 200:
            print("✅ Logged in successfully.")
        else:
            print(f"❌ Login failed: {login_resp.status_code}")
            sys.exit(1)
            
        # 2. Create Reservation
        res_payload = {
            "customer_name": "Test User",
            "customer_phone": "123456789",
            "rental_type": "hours",
            "start_date": "2020-01-01", # Past date to prove validations are bypassed
            "end_date": "2020-01-01",
            "start_hour": 8,
            "end_hour": 10,
            "payment_method": "cash",
            "items": [{"category_id": "cat-aluminio", "quantity": 100}] # Impossible stock to prove validations are bypassed
        }
        
        print("Creating admin reservation...")
        create_resp = session.post(f"{BASE_URL}/api/admin/reservations", json=res_payload)
        
        if create_resp.status_code == 200:
            data = create_resp.json()
            print(f"✅ Admin reservation created successfully: {data}")
            return data.get('reservation_id')
        else:
            print(f"❌ Admin reservation creation failed: {create_resp.status_code} - {create_resp.text}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error during admin reservation test: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_pricing_cap()
    res_id = test_admin_reservation()
    
    if res_id:
        print("\n--- Cleaning up... ---")
        session = requests.Session()
        session.post(f"{BASE_URL}/admin/login", json={"username": "admin", "password": "bicisi2024"})
        del_resp = session.delete(f"{BASE_URL}/api/admin/reservations/{res_id}")
        if del_resp.status_code == 200:
            print("✅ Test reservation deleted.")
        else:
            print(f"⚠️ Failed to delete test reservation: {del_resp.status_code}")
    
    print("\n🎉 ALL TESTS PASSED!")
