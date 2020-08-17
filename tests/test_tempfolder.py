import unittest
import pathlib
import re
import shutil
import tempfile
from czi_stitcher import TempFolder


class TestTempFolder(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.test_dir_path = pathlib.Path(self.test_dir)

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def test_create_with_full_path(self):
        # Test the creation of a temp folder by supplying new folder path
        temp_folder_path = self.test_dir_path / 'temp_folder'
        temp_folder = TempFolder(temp_folder_path)
        temp_folder.create()
        self.assertTrue(temp_folder_path.is_dir())

    def test_create_with_parent_path(self):
        # Test the creation of a temp folder by supplying parent folder path
        parent_folder_path = self.test_dir_path
        temp_folder = TempFolder(parent_folder_path=parent_folder_path)
        temp_folder.create()
        pattern = r'([A-Z]|[0-9]){8}'
        match = False
        for path in parent_folder_path.iterdir():
            if re.match(pattern, path.name):
                match = True
                break
        self.assertTrue(match)

    def test_purge(self):
        temp_folder_path = self.test_dir_path / 'temp_folder'
        temp_folder = TempFolder(temp_folder_path)
        temp_folder.create()
        # Create a sub folder and put a file in it
        sub_folder_path = (temp_folder_path / 'sub_folder')
        sub_folder_path.mkdir()
        (sub_folder_path / 'test_file.txt').touch()
        # Purge the folder
        temp_folder.purge()
        # Make sure the temp folder still exists
        self.assertTrue(temp_folder_path.is_dir())
        # Make sure there are no files or folders in the temp folder
        num_files = len(list(temp_folder_path.glob('**/*')))
        self.assertEqual(num_files, 0)

    def test_remove(self):
        temp_folder_path = self.test_dir_path / 'temp_folder'
        temp_folder = TempFolder(temp_folder_path)
        temp_folder.create()
        sub_folder_path = (temp_folder_path / 'sub_folder')
        sub_folder_path.mkdir()
        (sub_folder_path / 'test_file.txt').touch()
        temp_folder.remove()
        self.assertFalse(temp_folder_path.is_dir())


if __name__ == '__main__':
    unittest.main()
