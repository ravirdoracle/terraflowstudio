"""Network access must protect both pages and privileged APIs."""
import base64
import os
import unittest
from unittest.mock import patch

from app import app


class TestNetworkAuthentication(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {
            'APP_AUTH_USER': 'review-admin',
            'APP_AUTH_PASSWORD': 'review-password',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def credentials(self, password='review-password'):
        value = base64.b64encode(f'review-admin:{password}'.encode()).decode()
        return {'Authorization': f'Basic {value}'}

    def test_all_pages_and_privileged_apis_require_credentials(self):
        for method, path in [('GET', '/'), ('GET', '/api/config'),
                             ('POST', '/api/config'), ('POST', '/api/github/push')]:
            with self.subTest(path=path, method=method):
                response = self.client.open(path, method=method, json={})
                self.assertEqual(response.status_code, 401)
                self.assertIn('Basic', response.headers['WWW-Authenticate'])
                self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_wrong_password_does_not_grant_access(self):
        response = self.client.get('/api/config', headers=self.credentials('wrong'))
        self.assertEqual(response.status_code, 401)

    def test_correct_credentials_allow_the_app(self):
        response = self.client.get('/', headers=self.credentials())
        self.assertEqual(response.status_code, 200)

    def test_partial_configuration_fails_closed(self):
        for key in ('APP_AUTH_USER', 'APP_AUTH_PASSWORD'):
            with self.subTest(key=key), patch.dict(os.environ, {key: ''}):
                response = self.client.get('/', headers=self.credentials())
                self.assertEqual(response.status_code, 503)

    def test_existing_loopback_setup_without_credentials_still_works(self):
        with patch.dict(os.environ, {'APP_AUTH_USER': '', 'APP_AUTH_PASSWORD': ''}):
            self.assertEqual(self.client.get('/').status_code, 200)
