import logging
import httpx
 
from app.core.config import settings
 
logger = logging.getLogger(__name__)
 
def _get_storage_url():
    return f"{settings.supabase_url}/storage/v1/object"

# QR code storage buckets and helpers removed as per user request.
# Keeping the structure in case future storage needs arise.
