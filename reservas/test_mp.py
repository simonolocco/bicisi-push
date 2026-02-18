import mercadopago
import json

# Credentials provided
ACCESS_TOKEN = "TEST-4089125859574058-021718-384a315e4f5076feb41079180109d5fd-1471579186"

sdk = mercadopago.SDK(ACCESS_TOKEN)

preference_data = {
    "items": [
        {
            "title": "Test Item",
            "quantity": 1,
            "unit_price": 100.0,
            "currency_id": "ARS"
        }
    ],
    "payer": {
        "name": "Test User",
        "email": "test_user@test.com"
    },
    "back_urls": {
        "success": "http://localhost:5001/success",
        "failure": "http://localhost:5001/failure",
        "pending": "http://localhost:5001/pending"
    },
    "auto_return": "approved"
}

with open("mp_output.txt", "w") as f:
    f.write("Attempting to create preference...\n")
    try:
        preference_response = sdk.preference().create(preference_data)
        f.write(f"Response status: {preference_response.get('status')}\n")
        f.write(f"Response body: {json.dumps(preference_response, indent=2)}\n")
        
        if "response" in preference_response and "init_point" in preference_response["response"]:
            f.write(f"SUCCESS! Init point: {preference_response['response']['init_point']}\n")
        else:
            f.write("FAILED to get init_point\n")
            if "status" in preference_response and preference_response["status"] == 400:
                 f.write(f"Error cause: {json.dumps(preference_response.get('response', {}), indent=2)}\n")

    except Exception as e:
        f.write(f"EXCEPTION: {str(e)}\n")
