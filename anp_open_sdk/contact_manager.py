class ContactManager:
    def __init__(self, user_data):
        self.user_data = user_data  # BaseUserData 实例
        self._contacts = {}  # did -> contact dict
        self._token_to_remote = {}  # did -> token dict
        self._token_from_remote = {}  # did -> token dict
        self._load_contacts()

    def _load_contacts(self):
        # 加载联系人和 token 信息到缓存
        for contact in self.user_data.list_contacts():
            did = contact['did']
            self._contacts[did] = contact
            token_to = self.user_data.get_token_to_remote(did)
            if token_to:
                self._token_to_remote[did] = token_to
            token_from = self.user_data.get_token_from_remote(did)
            if token_from:
                self._token_from_remote[did] = token_from

    def add_contact(self, contact: dict):
        did = contact['did']
        self._contacts[did] = contact
        self.user_data.add_contact(contact)

    def get_contact(self, did: str):
        return self._contacts.get(did)

    def list_contacts(self):
        return list(self._contacts.values())

    def store_token_to_remote(self, remote_did: str, token: str, expires_delta: int):
        self.user_data.store_token_to_remote(remote_did, token, expires_delta)
        self._token_to_remote[remote_did] = self.user_data.get_token_to_remote(remote_did)

    def get_token_to_remote(self, remote_did: str):
        return self._token_to_remote.get(remote_did)

    def store_token_from_remote(self, remote_did: str, token: str):
        self.user_data.store_token_from_remote(remote_did, token)
        self._token_from_remote[remote_did] = self.user_data.get_token_from_remote(remote_did)

    def get_token_from_remote(self, remote_did: str):
        return self._token_from_remote.get(remote_did)

    def revoke_token_to_remote(self, remote_did: str):
        self.user_data.revoke_token_to_remote(remote_did)
        self._token_to_remote.pop(remote_did, None)

    def revoke_token_from_remote(self, target_did: str):
        """撤销与目标DID相关的本地token"""
        if target_did in self._token_from_remote:
            self._token_from_remote[target_did]["is_revoked"] = True
