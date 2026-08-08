import os
from locust import HttpUser, task, between

API_KEY = os.getenv("TEST_API_KEY", "ak_live_dario123456789")

class AegisGuardUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def send_chat_completion(self):
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama3",
            "messages": [
                {"role": "user", "content": "¿Cuál es la capital de España?"}
            ],
            "stream": False
        }

        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            headers=headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate Limit Exceeded (429)")
            else:
                response.failure(f"Error HTTP {response.status_code}: {response.text}")