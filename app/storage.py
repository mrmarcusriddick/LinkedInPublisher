import json
from contextlib import contextmanager
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError, HttpResponseError

class Busy(Exception):
    pass

class Store:
    def __init__(self, account, credential=None):
        self.credential = credential or DefaultAzureCredential()
        self.service = BlobServiceClient(f'https://{account}.blob.core.windows.net', credential=self.credential)

    def get_day(self, day):
        try:
            return json.loads(self.service.get_blob_client('queue', day + '.json').download_blob().readall())
        except ResourceNotFoundError:
            return None

    def import_day(self, day, data):
        blob = self.service.get_blob_client('queue', day + '.json')
        try:
            blob.upload_blob(data, overwrite=False, content_settings=ContentSettings(content_type='application/json'))
            return 'imported'
        except ResourceExistsError:
            if blob.download_blob().readall() != data:
                raise ValueError(f'{day}: queue is immutable; pause publishing before an operator replaces it')
            return 'unchanged'

    @contextmanager
    def locked_state(self, key):
        blob = self.service.get_blob_client('state', key + '.json')
        try:
            blob.upload_blob(b'{}', overwrite=False)
        except ResourceExistsError:
            pass
        try:
            lease = blob.acquire_lease(lease_duration=60)
        except HttpResponseError as e:
            if e.status_code == 409:
                raise Busy(key) from e
            raise
        try:
            state = json.loads(blob.download_blob(lease=lease).readall())
            def save(value):
                blob.upload_blob(json.dumps(value).encode(), overwrite=True, lease=lease)
            yield state, save
        finally:
            lease.release()
