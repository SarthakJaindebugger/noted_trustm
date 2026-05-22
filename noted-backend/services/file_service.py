import os
import uuid
from fastapi import UploadFile
import aiofiles
import logging

logger = logging.getLogger(__name__)

async def save_upload_file(upload_file: UploadFile, destination_dir: str) -> str:
    """
    Saves an uploaded file to a destination directory with a unique name.

    Args:
        upload_file: The file uploaded via a FastAPI endpoint.
        destination_dir: The directory where the file should be saved.

    Returns:
        The full path to the saved file.
    """
    try:
        # Sanitize filename and create a unique name to avoid collisions
        original_filename = upload_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in ('.', '_', '-')).strip()
        unique_id = str(uuid.uuid4())[:8]
        filename_base, file_extension = os.path.splitext(safe_filename)
        unique_filename = f"{filename_base}_{unique_id}{file_extension}"
        
        filepath = os.path.join(destination_dir, unique_filename)
        
        # Asynchronously write the file in chunks
        async with aiofiles.open(filepath, 'wb') as out_file:
            while content := await upload_file.read(1024 * 1024):  # Read in 1MB chunks
                await out_file.write(content)
        
        return filepath
    except Exception as e:
        logger.error(f"Could not save file {upload_file.filename}: {e}")
        raise