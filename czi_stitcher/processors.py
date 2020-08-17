
# Standard library imports
import sys
import pathlib
from pathlib import Path
import logging
from typing import Tuple, List
import argparse

import tqdm

# Third party package imports
from ashlar.scripts import ashlar
import jnius_config
import skimage.io

# Local module imports
from tempfolder import TempFolder
from utils import run_command

if not jnius_config.vm_running:
    bf_jar_path = 'jars/loci_tools.jar'
    jnius_config.add_classpath(bf_jar_path)
    # jnius_config.add_options('-Xmx8192m')

import jnius

ROOTDIR = str(pathlib.Path(__file__).parent.absolute())
IMAGEJPATH = '/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx'

# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Avoid the log4j "No appenders could be found" warning
DebugTools = jnius.autoclass('loci.common.DebugTools')
DebugTools.enableLogging("ERROR")

# Get Java classes
MetadataRetrieve = jnius.autoclass('ome.xml.meta.MetadataRetrieve')
ServiceFactory = jnius.autoclass('loci.common.services.ServiceFactory')
OMEXMLService = jnius.autoclass('loci.formats.services.OMEXMLService')
ImageReader = jnius.autoclass('loci.formats.ImageReader')
OMETiffWriter = jnius.autoclass('loci.formats.out.OMETiffWriter')
OMEXMLMetadataRoot = jnius.autoclass('ome.xml.meta.OMEXMLMetadataRoot')
PositiveInteger = jnius.autoclass('ome/xml/model/primitives/PositiveInteger')
TiffParser = jnius.autoclass('loci.formats.tiff.TiffParser')
TiffSaver = jnius.autoclass('loci.formats.tiff.TiffSaver')
RandomAccessInputStream = jnius.autoclass(
    'loci.common.RandomAccessInputStream')
OMEPyramidStore = jnius.autoclass('loci.formats.ome.OMEPyramidStore')
IMetaData = jnius.autoclass('loci.formats.meta.IMetadata')
DynamicMetadataOptions = jnius.autoclass(
    'loci.formats.in.DynamicMetadataOptions')


def tiles_to_stacks(input_path: Path,
                    output_path: Path,
                    tile_size_x: int = 2048,
                    tile_size_y: int = 2048) -> Path:
    '''Converts tiles from czi mosaic files to stacks. Useful for BaSiC shading
    correction, which requires stacks as input.

    Args:
        image_path (Path): Path to input image.
        output_path (Path): Path for output image.

    Raises:
        FileNotFoundError: Raised if input file cannot be found.

    Returns:
        Path: Path to output image.
    '''

    # Assert correct types before calling Java classes
    try:
        assert isinstance(input_path, Path)
        assert isinstance(output_path, Path)
    except AssertionError:
        logger.error("Make sure all paths are passed as Path objects.")
        raise TypeError("expected Path object")

    if not input_path.exists():
        logger.error("Input file '%s' does not exist.",
                     str(input_path.absolute()))
        raise FileNotFoundError
    if output_path.exists():
        logger.info("Stacked tiles already exist. Skipping conversion...")
        logger.debug("Output file '%s' already exists. Skipping conversion to "
                     "stacked image.", str(input_path.absolute()))
        # raise FileExistsError  # maybe want to make this an exception?
    else:
        factory = ServiceFactory()
        service = jnius.cast(OMEXMLService, factory.getInstance(OMEXMLService))
        metadata = service.createOMEXMLMetadata()

        # Initate reader
        reader = ImageReader()
        reader.setMetadataStore(metadata)
        # Turn off autostitching
        options = DynamicMetadataOptions()
        options.setBoolean('zeissczi.autostitch', False)
        reader.setMetadataOptions(options)
        reader.setId(str(input_path))

        # tile_size_x = reader.getOptimalTileWidth()
        # tile_size_y = reader.getOptimalTileHeight()

        # Initiate writer
        writer = OMETiffWriter()
        writer.setMetadataRetrieve(metadata)
        # writer.setTileSizeX(tile_size_x)
        # writer.setTileSizeY(tile_size_y)
        writer.setId(str(output_path))

        seriesCount = reader.getSeriesCount()

        logger.info("Converting tiled image to stacked.")
        for s in tqdm.trange(seriesCount):
            writer.setSeries(s)
            reader.setSeries(s)
            planeCount = reader.getImageCount()
            for p in range(planeCount):
                plane = reader.openBytes(p)
                writer.saveBytes(p, plane)

        writer.close()
        reader.close()

    return output_path


def merge_channels(image_paths: List[Path],
                   metadata_path: Path,
                   output_path: Path,
                   metadata_funcs=[]) -> Path:
    '''Combines separated channel files into a single file and adds metadata
    from the specified file.

    Args:
        image_paths (List[Path]): a list of image file paths
        metadata_path (Path): an image file containing the desired metadata
        output_path (Path): path for the resultant combined channel file

    Returns:
        Path: path to the output file
    '''

    # Should assert correct types before calling Java classes
    try:
        for path in image_paths:
            assert isinstance(path, Path)
        assert isinstance(metadata_path, Path)
        assert isinstance(output_path, Path)
    except AssertionError:
        logger.error("Make sure all paths are passed as Path objects.")
        raise TypeError("expected Path object")

    logger.info("Merging %i channels.", len(image_paths))
    logger.debug("Merging channels '%s'. Output set to '%s'. Metadata being "
                 "read from '%s'.", str(image_paths), str(metadata_path),
                 str(output_path))

    # each image path should only have one plane
    image_shape = get_image_shape(image_paths[0])

    factory = ServiceFactory()
    service = jnius.cast(OMEXMLService, factory.getInstance(OMEXMLService))
    metadata = service.createOMEXMLMetadata()

    # Set up Bio-Formats reader
    reader = ImageReader()
    reader.setMetadataStore(metadata)
    reader.setId(str(metadata_path))
    reader.close()

    root = jnius.cast(OMEXMLMetadataRoot, metadata.getRoot())

    # Get <Image> and <Pixels> from metadata of first image
    imageMeta = root.getImage(0)
    imageMeta.setName(output_path.name)
    pixelMeta = root.getImage(0).getPixels()

    # Update image size for <Pixels>
    pixelMeta.setSizeX(PositiveInteger(image_shape[1]))
    pixelMeta.setSizeY(PositiveInteger(image_shape[0]))
    imageMeta.setPixels(pixelMeta)

    # Delete all old <Image>'s
    while root.sizeOfImageList() > 0:
        root.removeImage(root.getImage(0))

    # Add the <Image> with updated image shape back to the metadata
    root.addImage(imageMeta)
    metadata.setRoot(root)

    # process metadata
    for func in metadata_funcs:
        metadata = func(metadata)

    # writer.setBigTiff(True)  # How to tell when to use bigtiff?

    # If output file already exists the writer will try to append to the file
    # so it needs to be deleted
    if output_path.exists():
        output_path.unlink()
    writer = OMETiffWriter()
    writer.setMetadataRetrieve(metadata)
    writer.setId(str(output_path))
    writer.setSeries(0)

    for i, img in enumerate(image_paths):
        logger.info("Writing plane %i", i)
        reader = ImageReader()
        reader.setId(str(img))
        plane = reader.openBytes(0)
        writer.saveBytes(i, plane)
        reader.close()
    writer.close()

    return output_path


def search_for_files(folder_path: Path, glob_pattern: str) -> List[Path]:
    '''Searches with glob pattern for files in the given folder path

    Args:
        folder_path (Path): Path to the folder to search
        glob_pattern (str): Name with wildcard (`*`) to search

    Returns:
        List[Path]: Paths to found files
    '''
    return list(folder_path.glob(glob_pattern))


def get_image_shape(image_path: Path) -> Tuple[int]:
    '''Gets the dimenions of an image from a file

    Args:
        image_path (Path): path to the image file

    Returns:
        Tuple[int]: tuple of image dimesions
    '''
    return skimage.io.imread(str(image_path)).shape


def add_experimenter_data(metadata, user_info: dict,
                          experimenter_index: int = 0):
    '''Updates metadata object to include experimenter information

    Args:
        metadata ([type]): OMEXMLMetadata object
        user_info ():
        experimenter_index (int, optional): experimenter index. Defaults to 0.

    Returns:
        [type]: OMEXMLMetadata object
    '''

    first_name = user_info['first_name']
    # middle_name = user_info['middle_name']
    last_name = user_info['last_name']
    email = user_info['email']
    institution = user_info['institution']

    # Update experimenter metadata
    metadata.setExperimenterEmail(email, experimenter_index)
    metadata.setExperimenterFirstName(first_name, experimenter_index)
    metadata.setExperimenterLastName(last_name, experimenter_index)
    metadata.setExperimenterInstitution(institution, experimenter_index)

    return metadata


def fix_filters_metadata(metadata):
    '''Fluorescence widefield image files converted from czi to ome-tiff may
    contain a weird filter set-up in the ome-xml. This condenses all the
    filters into one FilterSet.

    Args:
        metadata ([type]): OMEXMLMetadata object

    Returns:
        [type]: OMEXMLMetadata object
    '''

    # Convert metadata to an explorable `root` object
    root = jnius.cast(OMEXMLMetadataRoot, metadata.getRoot())
    instrument = root.getInstrument(0)
    kept_filter_set = None  # this line prevents a linter warning

    # Loop through each image
    image_count = metadata.getImageCount()
    for im in range(image_count):
        pixels = root.getImage(im).getPixels()
        # Loop through each channel
        channel_count = metadata.getChannelCount(im)
        for ch in range(channel_count):
            channel = pixels.getChannel(ch)
            filter_set = channel.getLinkedFilterSet()
            # Set filtersetref of first channel for use by the other channels
            if ch == 0:
                kept_filter_set = channel.getLinkedFilterSet()
            if ch > 0:
                # Reassign filter set
                channel.linkFilterSet(kept_filter_set)

                # Remove old filter set from instrument
                instrument.removeFilterSet(filter_set)

                # Remove dicroic filter from instrument
                dichroic = filter_set.getLinkedDichroic()
                instrument.removeDichroic(dichroic)

                # Remove excitation and emission filters
                excit_filters = filter_set.copyLinkedExcitationFilterList()
                emiss_filters = filter_set.copyLinkedEmissionFilterList()

                for filt in excit_filters:
                    instrument.removeFilter(filt)

                for filt in emiss_filters:
                    instrument.removeFilter(filt)

    metadata.setRoot(root)
    return metadata


def make_shading_profiles(image_path: Path,
                          output_dir: Path,
                          experiment_name: str = 'shading'
                          ) -> Tuple[Path, Path]:
    '''Creates flatfield and darkfield profiles from an image stack.

    Args:
        image_file (Path): path to input image file.
        output_dir (Path): path to output folder for shading profiles.
        experiment_name (str, optional): base name output images.
            Defaults to 'shading'.

    Returns:
        Tuple[Path, Path]: a tuple of file paths to the shading profile files.
    '''

    # Should assert correct types before calling Java classes
    try:
        assert isinstance(image_path, Path)
        assert isinstance(output_dir, Path)
    except AssertionError:
        logger.error("Make sure all paths are passed as Path objects.")
        raise TypeError("expected Path object")

    ffp_path = output_dir / (experiment_name + '-ffp-basic.tif')
    dfp_path = output_dir / (experiment_name + '-dfp-basic.tif')

    if ffp_path.exists() and dfp_path.exists():
        logger.info('Shading profiles already exist. Skipping calculations...')
    else:
        logger.info('Calculating shading profiles.')
        script_path = pathlib.Path(
            '/Users/tim/Projects/image-processing/czi-stitcher/czi_stitcher/'
            'scripts/imagej_basic_ashlar.py')
        if script_path.exists():
            logger.debug('Found BaSiC illumination correction script')
        else:
            logger.error('Could not find BaSiC illumination correction script.'
                         ' Check the script path: %s', str(script_path))

        cmd = \
            f'{IMAGEJPATH} --ij2 --headless --run ' \
            f'{script_path} ' \
            f'"filename=\'{image_path}\',' \
            f'output_dir=\'{output_dir}\',' \
            f'experiment_name=\'{experiment_name}\'"'
        run_command(cmd)

        logger.debug('Shading profiles written to %s, %s',
                     str(ffp_path), str(dfp_path))

    return str(ffp_path), str(dfp_path)


def stitch_image(image_files: List[Path],
                 output: Path = Path('.'),
                 align_channel: int = 0,
                 flip_x: bool = False,
                 flip_y: bool = False,
                 output_channels: List[int] = [],
                 maximum_shift: float = 15.0,
                 filter_sigma: float = 0.0,
                 filename_format: str = 'stitched_ch_{channel}.tif',
                 pyramid: bool = False,
                 tile_size: int = 1024,
                 ffp: List[Path] = [],
                 dfp: List[Path] = [],
                 plates: bool = False,
                 quiet: bool = False) -> List[Path]:

    output_path = pathlib.Path(output)
    image_files = [pathlib.Path(img_file) for img_file in image_files]

    if not isinstance(image_files, list):
        image_files = [image_files]

    if not output_path.exists():
        logger.error(
            "Output directory '%s' does not exist", str(output))

    ffp_paths = ffp
    if ffp_paths:
        if len(ffp_paths) not in (0, 1, len(image_files)):
            logger.error(
                f"Wrong number of flat-field profiles. Must be 1, or "
                f"{len(image_files)} (number of input files)"
            )
            return
        if len(ffp_paths) == 1:
            ffp_paths = ffp_paths * len(image_files)

    dfp_paths = dfp
    if dfp_paths:
        if len(dfp_paths) not in (0, 1, len(image_files)):
            logger.error(
                f"Wrong number of dark-field profiles. Must be 1, or "
                f"{len(image_files)} (number of input files)"
            )
            return
        if len(dfp_paths) == 1:
            dfp_paths = dfp_paths * len(image_files)

    aligner_args = {}
    aligner_args['channel'] = align_channel
    aligner_args['verbose'] = not quiet
    aligner_args['max_shift'] = maximum_shift
    aligner_args['filter_sigma'] = filter_sigma

    mosaic_args = {}
    if output_channels:
        mosaic_args['channels'] = output_channels
    if pyramid:
        mosaic_args['tile_size'] = tile_size
    if quiet is False:
        mosaic_args['verbose'] = True

    if plates:
        raise NotImplementedError
    elif list(output_path.glob(filename_format.format(channel='*'))):
        logger.info('Stitched files already exist. Skipping calculations...')
    else:
        print('starting conversion')
        mosaic_path_format = str(output_path / filename_format)

        filepaths = [str(img) for img in image_files]
        ashlar.process_single(
            filepaths, mosaic_path_format, flip_x, flip_y, ffp_paths,
            dfp_paths, aligner_args, mosaic_args, pyramid, quiet
        )

    output_paths = search_for_files(output,
                                    filename_format.format(channel='*'))
    return sorted(output_paths)


def process_image(input_path: Path, tmp_folder: Path, output_path: Path,
                  metadata_correction: bool = True):
    stacked = tiles_to_stacks(input_path, tmp_folder / 'stacked.ome.tif')
    ffp, dfp = make_shading_profiles(stacked, tmp_folder)
    stitched = stitch_image(
        [stacked], tmp_folder, flip_y=True, ffp=[ffp], dfp=[dfp])

    user_info = {
        'first_name': 'Tim',
        'middle_name': None,
        'last_name': 'Morello',
        'email': 'tdmorello@gmail.com',
        'institution': 'Downstate'
    }

    metadata_funcs = [
        lambda metadata: add_experimenter_data(metadata, user_info),
        fix_filters_metadata
    ]

    merge_channels(stitched, stacked, output_path,
                   metadata_funcs=metadata_funcs)


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(
        description='Stitch and align a multi-series image'
    )
    parser.add_argument(
        'filepaths', metavar='FILE', nargs='+',
        help='image files to be processed'
    )
    parser.add_argument(
        '-o', '--output', dest='output', default='.', metavar='DIR',
        help='output location of processed image; default is current directory'
    )
    parser.add_argument(
        '--flip-x', dest='flip_x', default=False, action='store_true',
        help=('flip tile positions left-to-right to account for unusual'
              ' microscope configurations')
    )
    parser.add_argument(
        '--flip-y', dest='flip_y', default=False, action='store_true',
        help=('flip tile positions top-to-bottom to account for unusual'
              ' microscope configurations')
    )
    arg_f_default = 'cycle_{cycle}_ch_{channel}.tif'
    parser.add_argument(
        '-f', '--filename-format', dest='filename_format',
        default=arg_f_default, metavar='FORMAT',
        help=(f'use FORMAT to generate output filenames, with {{cycle}} and'
              f' {{channel}} as required placeholders for the cycle and'
              f' channel numbers; default is {arg_f_default}')
    )
    default_tmp_dir = ('/Users/tim/Projects/image-processing/czi-stitcher/'
                       'czi_stitcher/data/tmp')
    parser.add_argument(
        '--tmp', '-tmp-directory', dest='tmp_dir', default=default_tmp_dir,
        metavar='DIR', type=str, help='Location for temp folder'
    )

    args = parser.parse_args(argv[1:])
    filepaths = [pathlib.Path(path) for path in args.filepaths]
    output_dir = pathlib.Path(args.output)
    # filename_format = args.filename_format
    # flip_x = args.flip_x
    # flip_y = args.flip_y
    tmp_dir = pathlib.Path(args.tmp_dir)

    for path in filepaths:

        path_basename = pathlib.Path(path).name.split('.')[0]
        # Create a temporary folder for intermediate files
        temp_folder = TempFolder(temp_folder_path=(tmp_dir / path_basename))
        temp_folder_path = temp_folder.path
        if not temp_folder_path.exists():
            temp_folder.create()
        output_path = output_dir / (path_basename + '.ome.tif')
        process_image(path, temp_folder_path, output_path)


if __name__ == "__main__":
    sys.exit(main())
