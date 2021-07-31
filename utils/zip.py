import os
from zipstream import AioZipStream
import aiofiles


async def get_packed_dir(dir_name: str):
    files = []
    for folder_name, subfolders, filenames in os.walk(dir_name):
        for filename in filenames:
            # create complete filepath of file in directory
            file_path = os.path.join(folder_name, filename)
            # Add file to zip
            files.append({'file': file_path,
                          'name': os.path.relpath(file_path,
                                                  os.path.join(dir_name, '..'))})

    if not os.path.exists('packed'):
        os.makedirs('packed')

    aiozip = AioZipStream(files)
    zip_filename = 'packed/' + dir_name + '.zip'
    zip_file = await aiofiles.open(zip_filename, 'wb')
    async for chunk in aiozip.stream():
        await zip_file.write(chunk)

    await zip_file.close()

    return zip_filename
