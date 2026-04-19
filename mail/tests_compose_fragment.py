from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from urllib.parse import parse_qs, urlparse

from .models import EmailAccount
from .views import _build_compose_action_urls


class ComposeFragmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='compose-user',
            password='secret1234',
        )
        self.url = reverse('compose_fragment')

    def _create_account(self):
        account = EmailAccount.objects.create(
            email='owner@example.com',
            imap_host='imap.example.com',
            imap_port=993,
            imap_username='owner@example.com',
            smtp_host='smtp.example.com',
            smtp_port=587,
            smtp_username='owner@example.com',
        )
        account.set_imap_password('imap-secret')
        account.set_smtp_password('smtp-secret')
        account.save(update_fields=['imap_password_encrypted', 'smtp_password_encrypted'])
        return account

    def test_compose_fragment_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_compose_fragment_rejects_post_method(self):
        self.client.login(username='compose-user', password='secret1234')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)

    def test_compose_fragment_renders_when_authenticated(self):
        self._create_account()
        self.client.login(username='compose-user', password='secret1234')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Compose')
        self.assertContains(response, reverse('send_message_api'))

    def test_compose_fragment_prefills_subject(self):
        self._create_account()
        self.client.login(username='compose-user', password='secret1234')

        response = self.client.get(self.url, {'subject': 'Re: Test message'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Re: Test message')


class ComposePageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='compose-page-user',
            password='secret1234',
        )
        self.url = reverse('compose_page')

    def _create_account(self):
        account = EmailAccount.objects.create(
            email='owner@example.com',
            imap_host='imap.example.com',
            imap_port=993,
            imap_username='owner@example.com',
            smtp_host='smtp.example.com',
            smtp_port=587,
            smtp_username='owner@example.com',
        )
        account.set_imap_password('imap-secret')
        account.set_smtp_password('smtp-secret')
        account.save(update_fields=['imap_password_encrypted', 'smtp_password_encrypted'])
        return account

    def test_compose_page_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_compose_page_rejects_post_method(self):
        self._create_account()
        self.client.login(username='compose-page-user', password='secret1234')

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)

    def test_compose_page_renders(self):
        self._create_account()
        self.client.login(username='compose-page-user', password='secret1234')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Compose')


class ComposePrefillUrlTests(TestCase):
    def test_reply_prefill_includes_recipient_and_reply_headers(self):
        class RawStub:
            def __init__(self, values):
                self._values = values

            def get(self, key):
                return self._values.get(key)

        message = {
            'sender': 'Jane Sender <jane@example.com>',
            'subject': 'Status update',
            'date': '2026-04-19 12:00',
            'body': 'First line\nSecond line',
            'raw': RawStub({
                'Message-ID': '<abc123@example.com>',
                'References': '<ref0@example.com>',
            }),
        }

        urls = _build_compose_action_urls(message)
        reply_query = parse_qs(urlparse(urls['reply_fragment_url']).query)
        forward_query = parse_qs(urlparse(urls['forward_fragment_url']).query)

        self.assertEqual(reply_query['to'][0], 'jane@example.com')
        self.assertEqual(reply_query['subject'][0], 'Re: Status update')
        self.assertEqual(reply_query['in_reply_to'][0], '<abc123@example.com>')
        self.assertIn('<ref0@example.com> <abc123@example.com>', reply_query['references'][0])
        self.assertEqual(forward_query['subject'][0], 'Fwd: Status update')
