#!/usr/bin/env python3
from loguru import logger
from pathlib import Path
from r2r import R2RClient
import subprocess
import sys
from time import sleep
import shlex
import argparse
import os

logger.remove()


project_root = [str(root) for root in Path(__file__).resolve().parents if str(root).endswith('R2R')][0]
compose_file = f"{project_root}{os.sep}docker{os.sep}compose.dev.yaml"
docker_dir = f"{project_root}{os.sep}docker"
dockerfile = f"{project_root}{os.sep}py{os.sep}Dockerfile"

def _run_command(command, capture_output=False, text=False, check=False, stream_output=False, cwd=None, print_command=True):
    """Helper function to run shell commands."""
    if print_command:
        print(f"Running command: {' '.join(map(shlex.quote, map(str, command)))}")
    try:
        if stream_output:
            # Use Popen for streaming output directly to stdout/stderr
            # This is better for commands like 'logs --follow' or 'restart' where we want immediate feedback
            process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr, text=True, cwd=cwd)
            process.wait() # Wait for the process to complete
            return subprocess.CompletedProcess(command, process.returncode) # Return a CompletedProcess-like object
        else:
            # Use run for non-streaming or capturing output
            result = subprocess.run(
                command, capture_output=capture_output, text=text, check=check, cwd=cwd
            )
            if result.returncode != 0:
                 # Don't print error here if capture_output is true, let caller handle it
                 if not capture_output:
                     print(f"❌ Command failed with exit code {result.returncode}", file=sys.stderr)

            return result
    except FileNotFoundError:
        print(f"Error: '{command[0]}' command not found. Is it installed and in PATH?", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while running command: {e}", file=sys.stderr)
        # Return a dummy failed process object if needed by caller
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=str(e))


def check_if_services_running(compose_file_path):
    """Check if any services defined in the compose file are running using docker CLI."""
    command = ["./activate.sh"
        "docker", "compose", "-f", str(compose_file_path), "ps",
        "--filter", "status=running", "-q",
    ]
    try:
        # Run quietly, capture output
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            # Don't print warning here, let the caller decide based on context
            # print(f"Warning: Could not check running services (docker compose ps failed): {result.stderr.strip()}", file=sys.stderr)
            return False # Assume not running if check fails or errors
        return bool(result.stdout.strip())
    except FileNotFoundError:
        print("Error: 'docker' command not found. Is Docker installed and in PATH?", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while checking running services: {e}", file=sys.stderr)
        return False # Assume not running on unexpected error


def docker_up(build: bool=False):
    """Start the Docker Compose services."""
    print("Starting Docker services...")

    print("Using:")
    print(f"  Compose file: {compose_file}")
    print(f"  Dockerfile: {dockerfile}") # Informational

    if build == True:
        command = ["docker", "compose", "-f", str(compose_file), "--profile", "postgres", "up", "-d", "--build"]
    else:
        command = ["docker", "compose", "-f", str(compose_file), "--profile", "postgres", "up", "-d"]

    # Stream output for build process visibility
    result = _run_command(command, check=False, cwd=str(docker_dir), stream_output=True)

    if result.returncode == 0:
        print("✅ Docker services started successfully")
    else:
        print(f"❌ Error starting Docker services (exit code: {result.returncode})")
        print("\nAttempting to show recent logs for 'r2r' service:")
        logs_command = ["docker", "compose", "-f", str(compose_file), "logs", "--tail=50", "r2r"]
        # Stream logs output as well
        _run_command(logs_command, check=False, cwd=str(project_root), stream_output=True)


def docker_down():
    """Stop the Docker Compose services defined in compose.dev.yaml."""
    print("Stopping Docker services defined in compose.dev.yaml...")
    command = ["docker", "compose", "-f", str(compose_file), "--profile", "postgres" ,"down", "--rmi", "local"]
    # Stream output for visibility
    result = _run_command(command, check=False, cwd=str(docker_dir), stream_output=True)

    if result.returncode == 0:
        print("✅ Docker services stopped successfully.")
    else:
        print(f"❌ Error stopping Docker services (exit code {result.returncode})")


def docker_logs():
    """Follow logs from Docker Compose services."""
    print("Following logs (Ctrl+C to stop)...")
    command = ["docker", "compose", "-f", str(compose_file), "logs", "--follow"]

    try:
        # Use Popen directly to handle KeyboardInterrupt more gracefully
        process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr, text=True, cwd=str(project_root))
        process.wait() # Wait for the process to complete (or be interrupted)
    except KeyboardInterrupt:
        print("\nStopped following logs.")
        # Attempt to terminate the process gracefully
        if process.poll() is None: # Check if process is still running
             try:
                 process.terminate()
                 process.wait(timeout=5) # Wait a bit for termination
             except subprocess.TimeoutExpired:
                 process.kill() # Force kill if terminate doesn't work
             except Exception as term_err:
                 print(f"Error terminating log process: {term_err}", file=sys.stderr)
    except FileNotFoundError:
         print(f"Error: '{command[0]}' command not found. Is it installed and in PATH?", file=sys.stderr)
         sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred while streaming logs: {e}", file=sys.stderr)


def docker_ps():
    """List Docker Compose services."""
    print("Listing services...")
    # Use docker's table format for clean output
    command = ["docker", "compose", "-f", str(compose_file), "ps"] # Default format is usually good

    # Capture output to check if it's empty
    result = _run_command(command, capture_output=True, text=True, check=False, cwd=str(project_root))

    if result.returncode == 0:
        output = result.stdout.strip()
        if output:
            # Check if output contains more than just the header
            lines = output.splitlines()
            if len(lines) > 1:
                print(output)
            else:
                 print("No R2R services are running.")
        else:
            # If stdout is empty, assume no services are running
            print("No R2R services are running.")
    else:
        # If the command failed, print the error
        print(f"❌ Error listing services (exit code: {result.returncode})")
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        elif result.stdout: # Sometimes errors go to stdout
            print(result.stdout.strip(), file=sys.stderr)


def docker_restart():
    """Restart Docker Compose services."""
    print("Restarting services...")
    command = ["docker", "compose", "-f", str(compose_file), "restart"]

    # Stream output for visibility
    result = _run_command(command, check=False, cwd=str(project_root), stream_output=True)

    if result.returncode == 0:
        print("✅ Services restarted.")
    else:
        print(f"❌ Error restarting services (exit code: {result.returncode})")


def _docker_exec_internal(container, command_to_run):
    """Internal logic for executing a command in a container."""
    print(f"Executing {' '.join(shlex.quote(c) for c in command_to_run)} in container '{container}'...")
    # Use 'docker compose exec' which is generally better for interactive shells
    docker_command = ["docker", "compose", "-f", str(compose_file), "exec", container] + command_to_run

    try:
        # Run the command, inheriting stdio for potential interactivity.
        # This allows the user's terminal to interact directly with the exec process.
        # Note: This might not create a fully interactive TTY in all environments/shells
        # compared to running `docker compose exec` directly, but it's the standard subprocess way.
        process = subprocess.Popen(docker_command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, cwd=str(project_root))
        exit_code = process.wait() # Wait for the command to finish

        if exit_code != 0:
             # Don't print error here, as the executed command's output/errors were already streamed.
             # The calling function should handle the exit code.
             pass
        return exit_code

    except FileNotFoundError:
         print(f"Error: 'docker' command not found. Is it installed and in PATH?", file=sys.stderr)
         return 1 # Return non-zero exit code
    except Exception as e:
        # Catch potential errors if the service doesn't exist or other docker issues
        print(f"\n❌ An error occurred executing command in container '{container}': {e}", file=sys.stderr)
        # Attempt to provide more context if possible (e.g., check if service exists)
        check_ps_command = ["docker", "compose", "-f", str(compose_file), "ps", "-q", container]
        # Run check quietly
        ps_result = _run_command(check_ps_command, capture_output=True, text=True, check=False, cwd=str(project_root), print_command=False)
        if ps_result.returncode != 0 or not ps_result.stdout.strip():
            print(f"Service '{container}' might not be running or doesn't exist.", file=sys.stderr)
        return 1 # Return non-zero exit code

def delete_single_collection(collection_id: str):
    """Delete a single collection by its ID and log the process."""
    logger.info(f"Attempting to delete collection with ID: <cyan>{collection_id}</cyan>")
    try:
        client = R2RClient("http://localhost:7272")

        try:
            # Attempt to delete the collection
            client.collections.delete(collection_id)
            # Log successful deletion
            logger.success(f"Successfully deleted collection: <cyan>{collection_id}</cyan>")
        except Exception as e:
            # Handle specific R2R errors, e.g., collection not found
            # The exact error message/type might vary depending on R2RClient implementation
            logger.error(f"Failed to delete collection <cyan>{collection_id}</cyan>. It might not exist or another error occurred: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while deleting collection <cyan>{collection_id}</cyan>: {e}")

    except Exception as e:
        logger.error(f"An error occurred during the single collection deletion process: {e}")

def delete_all_collections():
    """Delete all collections in the R2R database and log the process."""
    # Log a colorized warning message when the function starts
    logger.warning(
        "<yellow>Initiating deletion of ALL R2R database collections.</yellow> "
        "<red>This action is irreversible!</red>"
    )
    try:
        client = R2RClient("http://localhost:7272")
        logger.info("Fetching list of existing collections...")
        all_collections_list = client.collections.list()
        all_collections = [str(collection.id) for collection in [collections_obj[1] for collections_obj in all_collections_list][0]]

        if not all_collections:
            logger.info("No collections found to delete.")
            return

        logger.info(f"Found collections: {', '.join(all_collections)}")

        deleted_collections = []
        errors = []

        for collection_name in all_collections:
            try:
                logger.debug(f"Attempting to delete collection: {collection_name}")
                # Assuming client.collections.delete returns something on success or raises error
                result = client.collections.delete(id=collection_name)
                if result == True:
                    logger.success(f"Successfully deleted collection: <cyan>{collection_name}</cyan>")
                    deleted_collections.append(collection_name)
                else:
                    print(result)
                    logger.error(f"Failed to delete collection <cyan>{collection_name}</cyan>. It might not exist or another error occurred.")

            except Exception as e: # Catch unexpected errors
                logger.error(f"An unexpected error occurred while deleting collection <cyan>{collection_name}</cyan>: {e}")
                errors.append(collection_name)

        if deleted_collections:
             logger.info(f"Finished deletion process. Deleted: {len(deleted_collections)} collections.")
        if errors:
            logger.warning(f"Could not delete {len(errors)} collections: {', '.join(errors)}")

    except Exception as e:
        logger.error(f"An error occurred during the collection deletion process: {e}")

# /FIXME: When entering an email to user.delete() it returns 'collection not found'???
## As a SuperUser and the delete(password='') still saying 'collection not found'
"""
It seems like it does delete the error. But!

client.users.delete(usr_list[9].id, password='') returns 'collection not found'
But run a second time it replies 'User not found'
This is a bug in the R2RClient or the API.
"""
def delete_all_non_superusers():
    client = R2RClient("http://localhost:7272")
    logger.info("Fetching list of users...")
    errors = []
    for user in list(client.users.list())[0][1]:
        response = ""
        if user.is_superuser == False:
            try:
                logger.debug(f"Attempting to delete user: {user.email}")
                response = client.users.delete(user.id, password='')
                logger.success(f"Successfully deleted user: <white> {user.email}. </white> Response: {response}")
            except Exception as e:
                logger.error(f"Failed to delete user <white> {user.email} </white>: {e}\nRespose was: {response}")
                errors.append(user.email)
            sleep(1)
    if errors:
        logger.error(f"Could not delete {len(errors)} users: {', '.join(errors)}")


def up_command(build: bool = False):
    docker_up(build)

def down_command():
    docker_down()

def logs_command():
    docker_logs()

def ps_command():
    docker_ps()

def restart_command():
    docker_restart()

def exec_command():
    """Entry point for executing a command in a container."""
    # Assumes called via entry point like `r2r-exec [container] [command...]`
    # sys.argv will be ['r2r-exec', container, cmd_part1, cmd_part2, ...]
    args = sys.argv[1:] # Arguments after the command name itself
    container = args[0] if args else "r2r"
    command_to_run = args[1:] if len(args) > 1 else ["/bin/sh"] # Default to shell

    exit_code = _docker_exec_internal(container, command_to_run)
    sys.exit(exit_code) # Exit with the code from the executed command


def rmcollections_command(collection_id: str | None = None):
    """Entry point for deleting collections."""
    if collection_id:
        delete_single_collection(collection_id)
    else:
        # Add a confirmation step for deleting all collections
        confirm = input("Are you sure you want to delete ALL collections? This is irreversible. (yes/y/no/n): ")
        if confirm.lower() in ['yes', 'y']:
            delete_all_collections()
        else:
            logger.info("Operation cancelled by user.")

def rmallusers_command():
    """Entry point for deleting all non-superuser users."""
    delete_all_non_superusers()


def main():
    # CRITICAL, ERROR, WARNING are come under DEBUG and go out to stderr
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>\n<level>{message}</level>\n",
        colorize=True
    )

    logger.add(
        sys.stdout,
        level="INFO",
        filter=lambda record: record["level"].name in ("INFO", "SUCCESS"),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>",
        colorize=True
    )

    parser = argparse.ArgumentParser(description="R2R Development Tool (uvx)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    up_parser = subparsers.add_parser("up", help="Start Docker services (docker compose up)")
    up_parser.add_argument(["--build", "-b"], action="store_true", default=False, help="Build R2R Dockerfile before starting services")

    # Add subparsers for each command
    subparsers.add_parser("down", help="Stop Docker services (docker compose down)")
    subparsers.add_parser("logs", help="Follow Docker logs (docker compose logs --follow)")
    subparsers.add_parser("ps", help="List running services (docker compose ps)")
    subparsers.add_parser("restart", help="Restart services (docker compose restart)")

    # Exec command needs special handling for container and command arguments
    exec_parser = subparsers.add_parser("exec", help="Execute command in a container (docker compose exec)")
    exec_parser.add_argument("container", nargs='?', default="r2r", help="Target container name (default: r2r)")
    exec_parser.add_argument("container_command", nargs=argparse.REMAINDER, help="Command to run in container (default: /bin/sh)")

    # Remove Collections command
    rm_parser = subparsers.add_parser("rmcollections", help="Delete R2R collections. Deletes ALL if no ID is provided.")
    rm_parser.add_argument("collection_id", nargs='?', default=None, help="Optional ID of the specific collection to delete.")

    # Remove All Users command (NEW)
    subparsers.add_parser("rmallusers", help="Delete ALL non-superuser users from R2R.")


    args = parser.parse_args()

    if args.command == "up":
        up_command(args.build)
    elif args.command == "down":
        down_command()
    elif args.command == "logs":
        logs_command()
    elif args.command == "ps":
        ps_command()
    elif args.command == "restart":
        restart_command()
    elif args.command == "exec":
        cmd_to_run = args.container_command if args.container_command else ["/bin/sh"]
        exit_code = _docker_exec_internal(args.container, cmd_to_run)
        sys.exit(exit_code)
    elif args.command == "rmcollections":
        rmcollections_command(args.collection_id)
    elif args.command == "rmallusers":
        rmallusers_command()


if __name__ == "__main__":
    main()
