import unittest
from create_app import app

class TestSharedRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_register(self):
        response = self.client.post('/shared/register', json={
            'id': 'test123',
            'name': 'Test User',
            'role': 'student',
            'password': 'testpass'
        })
        self.assertEqual(response.status_code, 201)
