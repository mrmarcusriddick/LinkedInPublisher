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
        return self.import_blob(day + '.json', data, 'application/json')

    def import_blob(self, name, data, content_type):
        blob = self.service.get_blob_client('queue', name)
        try:
            blob.upload_blob(data, overwrite=False, content_settings=ContentSettings(content_type=content_type))
            return 'imported'
        except ResourceExistsError:
            if blob.download_blob().readall() != data:
                raise ValueError(f'{name}: queue is immutable; pause publishing before an operator replaces it')
            return 'unchanged'

    def get_media(self, day):
        try:
            data = self.service.get_blob_client('queue', 'media/' + day + '.json').download_blob().readall()
        except ResourceNotFoundError:
            return None
        from app.media import validate_media
        item = validate_media(json.loads(data))
        if item['date'] != day:
            raise ValueError('Attachment date mismatch')
        return item

    def get_asset(self, path):
        from app.media import MAX_BYTES
        blob = self.service.get_blob_client('queue', path)
        if blob.get_blob_properties().size > MAX_BYTES:
            raise ValueError('Image too large')
        return blob.download_blob(offset=0, length=MAX_BYTES + 1).readall()

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
