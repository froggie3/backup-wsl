import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from subprocess import PIPE, STDOUT, Popen, TimeoutExpired, run
from time import sleep

import psutil

def kill_process(name):
    for proc in psutil.process_iter(["pid", "name"]):
        if proc.info["name"] == name:
            try:
                proc.kill()
                logger.info("%s process killed successfully.", name)
                return True
            except psutil.AccessDenied:
                logger.critical("Access denied when trying to kill %s.", name)
            except psutil.NoSuchProcess:
                logger.critical("No such process: %s.", name)
            except Exception as error:
                logger.critical("An error occurred: %s", error)


def create_archive_compress(distro, save, vhdx):
    cmd = ["wsl.exe", "--export"]
    if vhdx:
        cmd.append("--vhd")
    with Popen([*cmd, distro, "-"], stdout=PIPE, stderr=STDOUT) as proc0:
        with Popen(["zstd.exe", "-o", save], stdin=proc0.stdout, stdout=PIPE) as proc1:
            try:
                logger.info("Compressing the archives...")
                outs, errs = proc1.communicate(timeout=3600 * 60)
                logging.info(outs.decode())
            except TimeoutExpired:
                proc1.kill()
                outs, errs = proc1.communicate()
            finally:
                return proc1.returncode


def create_archive(distro, save, vhdx):
    cmd = ["wsl.exe", "--export"]
    if vhdx:
        cmd.append("--vhd")
    res = run([*cmd, distro, save], shell=True, check=True)
    return res.returncode


def shutdown_wsl(distro):
    res = run(["wsl.exe", "--terminate", distro], shell=True, check=True)
    return res.returncode


def delete_garbage_file(save):
    try:
        os.remove(save)
    except OSError:
        logger.debug("Deletion of %s failed.", save)


def start_backup(distro, path, compress, vhdx):
    logger.info("Making a backup of %s to %s...", distro, path)
    try:
        if compress:
            endstat = create_archive_compress(distro, path, vhdx)
        else:
            endstat = create_archive(distro, path, vhdx)
        if endstat != 0:
            # expect some procedures for future
            pass
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        delete_garbage_file(path)
    except Exception:
        logger.exception("Backup of %s failed for some reasons.", distro)
        delete_garbage_file(path)
    else:
        logger.info("Backup of %s succeeded.", distro)
        return True
    finally:
        sys.exit(1)


def get_extension(vhdx, compress):
    if vhdx:
        ext = ".vhdx"
    else:
        ext = ".tar"
    if compress:
        ext += ".zst"
    return ext


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "parent_dir", type=str, help="the directory in which the archive is saved"
    )
    parser.add_argument(
        "distribution_name",
        type=str,
        help="the distro for which the archive is created",
    )
    parser.add_argument(
        "-c",
        "--compress",
        action="store_true",
        help="compress the archive using zstandard",
    )
    parser.add_argument(
        "--vhdx",
        action="store_true",
        help="archive the distribution in vhdx format",
    )
    parser.add_argument(
        "--explorer",
        action="store_true",
        help="open the dest folder with explorer.exe after the process",
    )
    parser.add_argument(
        '--loglevel',
        default='warning',
        help='provide logging level (default: %(default)s)'
    )

    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel.upper())
    logger = logging.getLogger(__name__)

    distribution_dir = os.path.join(args.parent_dir, args.distribution_name)
    file_name = f"{datetime.now().isoformat('T').replace(':', '-')}{get_extension(args.vhdx, args.compress)}"
    save_path = os.path.join(distribution_dir, file_name)

    for proc in psutil.process_iter(["pid", "name"]):
        if proc.info["name"] == "wsl.exe":
            logger.info("Shutting down the instance of %s...", args.distribution_name)
            if shutdown_wsl(args.distribution_name) != 0:
                sys.exit(1)
            else:
                logger.info("Waiting for a moment...")
                sleep(5)

    if (
        start_backup(args.distribution_name, save_path, args.compress, args.vhdx)
        is not None
    ):
        logger.info("Opening %s explorer...", args.parent_dir)
        if args.explorer:
            run(["explorer.exe", distribution_dir])
