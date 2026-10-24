import hashlib
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

from runtime_trust import with_local_ca


class LocalCATests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.ca = self.base / '.state' / 'tls' / 'approved-root.pem'
        self.ca.parent.mkdir(parents=True)
        self.data = b'-----BEGIN CERTIFICATE-----\nTEST-ONLY\n-----END CERTIFICATE-----\n'
        self.ca.write_bytes(self.data)
        self.launch = dict(extra_ca_file='tls/approved-root.pem',
                           extra_ca_sha256=hashlib.sha256(self.data).hexdigest())

    def load(self, launch=None, env=None):
        return with_local_ca(self.base, self.launch if launch is None else launch,
                             {'PATH': 'unchanged'} if env is None else env)

    def test_no_configuration_does_not_add_or_change_trust(self):
        old = {'PATH': 'unchanged', 'OTHER': 'preserved'}
        self.assertEqual(self.load({}, old), old)
        self.assertIsNot(self.load({}, old), old)

    def test_approved_ca_is_process_local_and_keeps_tls_validation(self):
        old = {'PATH': 'unchanged'}
        with patch('runtime_trust.ssl.SSLContext') as context:
            env = self.load(env=old)
        self.assertEqual(env, dict(PATH='unchanged', NODE_EXTRA_CA_CERTS=str(self.ca)))
        self.assertEqual(old, {'PATH': 'unchanged'})
        context.return_value.load_verify_locations.assert_called_once_with(cadata=self.data.decode())
        self.assertNotIn('NODE_TLS_REJECT_UNAUTHORIZED', env)
        self.assertNotIn('NODE_OPTIONS', env)

    def test_missing_hash_or_path_fails(self):
        for data in ({'extra_ca_file': 'tls/approved-root.pem'}, {'extra_ca_sha256': 'a' * 64}):
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                self.load(data)

    def test_invalid_configuration_types_and_hashes_fail(self):
        for field, value in [('extra_ca_file', 2), ('extra_ca_file', ''),
                             ('extra_ca_sha256', 2), ('extra_ca_sha256', 'g' * 64),
                             ('extra_ca_sha256', 'a' * 63)]:
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                self.load(dict(self.launch, **{field: value}))

    def test_absolute_and_parent_paths_fail(self):
        for name in (str(self.ca), '/outside.pem', '../outside.pem', 'tls/../../outside.pem',
                     r'C:\outside.pem', r'..\outside.pem', r'C:outside.pem', r'\\server\share\ca.pem'):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                self.load(dict(self.launch, extra_ca_file=name))

    def test_missing_ca_fails(self):
        self.ca.unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_changed_ca_fails(self):
        self.ca.write_bytes(self.data + b'changed')
        with self.assertRaises(RuntimeError):
            self.load()

    def test_oversized_ca_fails_even_with_matching_hash(self):
        data = b'x' * (128 * 1024 + 1)
        self.ca.write_bytes(data)
        with self.assertRaises(RuntimeError):
            self.load(dict(self.launch, extra_ca_sha256=hashlib.sha256(data).hexdigest()))

    def test_invalid_pem_is_rejected_by_real_tls_parser(self):
        with self.assertRaises(ssl.SSLError):
            self.load()

    def test_private_keys_and_bundles_fail(self):
        for data in (self.data + b'PRIVATE KEY', self.data * 2):
            self.ca.write_bytes(data)
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                self.load(dict(self.launch, extra_ca_sha256=hashlib.sha256(data).hexdigest()))

    def test_conflicting_inherited_ca_is_not_silently_overwritten(self):
        with patch('runtime_trust.ssl.SSLContext'), self.assertRaises(RuntimeError):
            self.load(env={'NODE_EXTRA_CA_CERTS': str(self.base / 'other.pem')})

    def test_same_inherited_ca_is_preserved(self):
        with patch('runtime_trust.ssl.SSLContext'):
            env = self.load(env={'NODE_EXTRA_CA_CERTS': str(self.ca)})
        self.assertEqual(env['NODE_EXTRA_CA_CERTS'], str(self.ca))

    def test_symlink_is_rejected(self):
        link = self.ca.parent / 'linked.pem'
        try:
            link.symlink_to(self.ca)
        except OSError:
            self.skipTest('Symlink creation unavailable for this account')
        with self.assertRaises(RuntimeError):
            self.load(dict(self.launch, extra_ca_file='tls/linked.pem'))

    def test_linked_parent_is_rejected_without_requiring_privileges(self):
        with patch('pathlib.Path.is_symlink', return_value=True), self.assertRaises(RuntimeError):
            self.load()

    def test_junction_is_rejected_without_requiring_privileges(self):
        with patch('pathlib.Path.is_junction', return_value=True, create=True), self.assertRaises(RuntimeError):
            self.load()


if __name__ == '__main__':
    unittest.main()
