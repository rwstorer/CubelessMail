from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import EmailAccount


class SendMessageApiTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username='tester',
			password='secret1234',
		)
		self.url = reverse('send_message_api')

	def _create_account(self, *, with_smtp=True):
		account = EmailAccount.objects.create(
			email='owner@example.com',
			imap_host='imap.example.com',
			imap_port=993,
			imap_username='owner@example.com',
			smtp_host='smtp.example.com' if with_smtp else '',
			smtp_port=587,
			smtp_username='owner@example.com' if with_smtp else '',
		)
		account.set_imap_password('imap-secret')
		if with_smtp:
			account.set_smtp_password('smtp-secret')
		account.save(update_fields=['imap_password_encrypted', 'smtp_password_encrypted'])
		return account

	def test_send_api_requires_authentication(self):
		response = self.client.post(
			self.url,
			data={'to': 'person@example.com', 'subject': 'Hello', 'text_body': 'Hi'},
		)
		self.assertEqual(response.status_code, 302)

	def test_send_api_rejects_get_method(self):
		self._create_account()
		self.client.login(username='tester', password='secret1234')

		response = self.client.get(self.url)
		self.assertEqual(response.status_code, 405)

	def test_send_api_rejects_missing_csrf_token(self):
		self._create_account()
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.login(username='tester', password='secret1234')

		response = csrf_client.post(
			self.url,
			data={'to': 'person@example.com', 'subject': 'Hello', 'text_body': 'Hi'},
		)
		self.assertEqual(response.status_code, 403)

	def test_send_api_returns_validation_errors(self):
		self._create_account()
		self.client.login(username='tester', password='secret1234')

		response = self.client.post(
			self.url,
			data={'subject': 'No recipient', 'text_body': 'Hello body'},
		)
		self.assertEqual(response.status_code, 400)
		payload = response.json()
		self.assertFalse(payload['ok'])
		self.assertIn('to', payload['errors'])

	def test_send_api_rejects_incomplete_smtp_config(self):
		self._create_account(with_smtp=False)
		self.client.login(username='tester', password='secret1234')

		response = self.client.post(
			self.url,
			data={'to': 'person@example.com', 'subject': 'Hello', 'text_body': 'Hi'},
		)
		self.assertEqual(response.status_code, 422)
		payload = response.json()
		self.assertFalse(payload['ok'])
		self.assertIn('smtp', payload['errors'])

	@patch('mail.views.SMTPEmailClient.send_email')
	@patch('mail.views.SMTPEmailClient.connect')
	@patch('mail.views.SMTPEmailClient.disconnect')
	def test_send_api_success(self, mock_disconnect, mock_connect, mock_send):
		self._create_account()
		self.client.login(username='tester', password='secret1234')

		response = self.client.post(
			self.url,
			data={
				'to': 'person@example.com',
				'cc': 'cc@example.com',
				'bcc': 'bcc@example.com',
				'subject': 'Hello',
				'text_body': 'Hi there',
				'html_body': '<p>Hi <strong>there</strong></p>',
			},
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload['ok'])
		mock_connect.assert_called_once()
		mock_send.assert_called_once()
		mock_disconnect.assert_called_once()
