import json
from .data_classes import GetMailboxesResponse

class SharedMailboxManager:
    def __init__(self, mailbox_data_path):
        with open(mailbox_data_path, 'r') as f:
            self.mailboxes_by_user = json.load(f)
    
    def validate_mailbox(self, user_email, mailbox_to_access):
        if user_email.lower() == mailbox_to_access.lower():
            return True
        shared_mailboxes = self.mailboxes_by_user.get(user_email.lower())
        if shared_mailboxes is not None:
            for box in shared_mailboxes:
                if box['shared_mailbox'].lower() == mailbox_to_access.lower() and 'FullAccess' in box['access_rights']:
                    return True 
        return False
    
    def list_shared_mailboxes(self, user_email):
        shared_mailboxes = self.mailboxes_by_user.get(user_email.lower(), [])
        shared_mailboxes = list(filter(lambda x: 'FullAccess' in x['access_rights'], shared_mailboxes))
        shared_mailboxes = [box['shared_mailbox'] for box in shared_mailboxes]
        shared_mailboxes.append(user_email)
        return GetMailboxesResponse(shared_mailboxes).to_json()