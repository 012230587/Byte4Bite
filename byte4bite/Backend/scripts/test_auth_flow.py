"""End-to-end API test: register, login, profile, save recipe, list saved."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
EMAIL = "testuser@byte4bite.com"
PASSWORD = "testpass123"


def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    print("=== Byte4Bite auth & saved recipes test ===\n")

    # Register (may fail if user exists — fall through to login)
    status, data = req("POST", "/api/auth/register", {"email": EMAIL, "password": PASSWORD})
    print(f"1. Register: HTTP {status}", data.get("email") or data.get("detail"))

    if status not in (200, 400):
        print("   FAILED")
        return

    # Login
    status, data = req("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    print(f"2. Login: HTTP {status}", "OK" if data.get("success") else data)
    if not data.get("access_token"):
        print("   FAILED — no token")
        return
    token = data["access_token"]

    # Profile GET
    status, data = req("GET", "/api/auth/profile", token=token)
    print(f"3. Get profile: HTTP {status}", data.get("profile", {}).get("email"))

    # Profile PUT
    status, data = req(
        "PUT",
        "/api/auth/profile",
        {
            "dietary_restriction": "vegetarian",
            "allergies": ["peanuts"],
            "health_goals": ["high_protein"],
        },
        token=token,
    )
    print(f"4. Update profile: HTTP {status}", data.get("profile", {}).get("dietary_restriction"))

    # Save recipe
    sample_recipe = {
        "title": "Test Saved Thai Basil Chicken",
        "description": "A quick test recipe for save flow.",
        "ingredients": ["300g chicken", "2 tbsp soy sauce", "1 cup basil"],
        "instructions": ["Prep ingredients (5 mins).", "Stir-fry chicken (10 mins).", "Serve hot (1 min)."],
        "prep_time": "20 mins",
        "difficulty": "Easy",
        "cuisine": "thai",
        "dietary_tags": ["halal"],
        "is_generated": True,
    }
    status, data = req("POST", "/api/auth/saved-recipes", {"recipe": sample_recipe, "notes": "test save"}, token=token)
    print(f"5. Save recipe: HTTP {status}", data.get("saved_recipe", {}).get("title") or data.get("detail"))

    # List saved
    status, data = req("GET", "/api/auth/saved-recipes", token=token)
    count = data.get("count", 0)
    print(f"6. List saved recipes: HTTP {status} count={count}")
    if count:
        print(f"   First saved: {data['recipes'][0]['title']}")

    print("\n=== All tests completed ===")


if __name__ == "__main__":
    main()
