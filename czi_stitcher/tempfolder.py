import pathlib
from pathlib import Path
from typing import Optional
import uuid
import shutil
import logging

logger = logging.getLogger(__name__)


class TempFolder:
    '''Creates and manages temporary directories'''

    def __init__(self,
                 temp_folder_path: Optional[Path] = None,
                 parent_folder_path: Optional[Path] = None):
        '''Creates a temporary folder. Good for having a location to store
           temporary or intermediary files and folders.

        Args:
            temp_folder_path (Path, optional): Desired path to temp
                folder. Defaults to None.
            parent_folder_path (Path, optional): Path to desired
                parent folder for temp folder. A random name is generated
                for the temp folder. Defaults to None.
        '''

        try:
            assert bool(temp_folder_path) ^ bool(parent_folder_path)
        except AssertionError as error:
            logger.error("TempFolder object not created. Either give a path to "
                         "the folder, or a path to the parent folder. Was "
                         "supplied folder path: '%s' and parent path: '%s'. %s",
                         temp_folder_path, parent_folder_path, error)
        else:
            if temp_folder_path is not None:
                self.path = pathlib.Path(temp_folder_path)
            elif parent_folder_path is not None:
                rand_id = str(uuid.uuid4()).upper()[:8]
                self.path = pathlib.Path(parent_folder_path) / rand_id
            else:
                logger.error("Cannot create '%s' object. Check '__init__' "
                             "arguments.", self.__class__.__name__)

    def create(self):
        '''Creates the temporary directory if it does not already exist'''
        try:
            logger.debug("Attempting to create directory at '%s'",
                         str(self.path.absolute()))
            self.path.mkdir()
            logger.debug("Created new directory at '%s'",
                         str(self.path.absolute()))
        except FileExistsError as error:
            logger.error("Cannot create directory '%s'. File already exists. "
                         "Remove it first or specify argument as parent folder"
                         "path. %s", str(self.path.absolute()), error)
        except OSError as error:
            logger.error("Cannot create directory '%s'. %s",
                         str(self.path.absolute()), error)

    def purge(self):
        '''Removes all files and sub-directories from the temp folder'''
        try:
            logger.debug("Attempting to remove files and sub-directories from "
                         "'%s'", str(self.path.absolute()))
            for sub in self.path.iterdir():
                if sub.is_dir():
                    shutil.rmtree(sub)
                else:
                    sub.unlink()
            logger.debug("Removed files and directories from '%s'",
                         str(self.path.absolute()))
        except FileNotFoundError as error:
            logger.error("Cannot purge directory '%s'. Folder does not exist. "
                         "%s", self.path.absolute(), error)
        except OSError as error:
            logger.error("There was a problem purging directory '%s'. %s",
                         str(self.path.absolute()), error)

    def remove(self):
        '''Removes the temporary directory if it exists'''
        try:
            self.purge()
            logger.debug("Removing directory '%s'.", self.path.absolute())
            self.path.rmdir()
            logger.debug("Removed directory '%s'.", self.path.absolute())
        except FileNotFoundError as error:
            logger.error("Cannot remove folder '%s'. File does not exist. %s",
                         str(self.path.absolute()), error)
        except OSError as error:
            logger.debug("There was a problem removing the directory '%s'. %s",
                         str(self.path.absolute()), error)


def main():
    pass


if __name__ == "__main__":
    pass
