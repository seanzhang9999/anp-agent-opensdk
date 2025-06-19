import argparse
import getpass
from app.services.user_service import create_user_with_anp # Ensure this path is correct
from app.models.schemas import UserCreate

def main():
    parser = argparse.ArgumentParser(description="Create a new ANP user for the chat extension.")
    parser.add_argument("username", help="The desired username for the chat extension.")
    # ANP specific args - make these match what your did_create_user expects
    parser.add_argument("--anp-name", help="Name for the ANP agent (e.g., 'Demo User Agent'). Defaults to username.")
    parser.add_argument("--anp-host", default="localhost", help="Host for ANP agent.")
    parser.add_argument("--anp-port", type=int, default=9527, help="Port for ANP agent.") # Example port
    parser.add_argument("--anp-dir", default="wba", help="Directory for ANP agent (e.g., 'wba').") # Example dir
    parser.add_argument("--anp-type", default="user", help="Type for ANP agent (e.g., 'user').")

    args = parser.parse_args()

    password = getpass.getpass(f"Enter password for user '{args.username}': ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        logger.debug("Passwords do not match. Exiting.")
        return

    user_create_data = UserCreate(
        username=args.username,
        password=password, # Plaintext, will be stored as is by user_service for demo
        anp_user_name=args.anp_name or args.username,
        anp_host=args.anp_host,
        anp_port=args.anp_port,
        anp_dir=args.anp_dir,
        anp_type=args.anp_type
    )

    logger.debug(f"Attempting to create user '{args.username}' with ANP agent name '{user_create_data.anp_user_name}'...")
    
    # Ensure PYTHONPATH is set so app.services.user_service can import anp_open_sdk
    # This script is run from backend_py directory.
    # If anp_open_sdk is in mcp-chat-extension/anp_open_sdk,
    # you might need to run with: PYTHONPATH=../:$PYTHONPATH python setup_anp_user.py ...
    
    did, error = create_user_with_anp(user_create_data)

    if error:
        logger.debug(f"Error creating user: {error}")
    else:
        logger.debug(f"User '{args.username}' created successfully!")
        logger.debug(f"DID: {did}")
        logger.debug(f"A 'personal_data' directory should now exist in their ANP user directory.")
        logger.debug("You can add text files to this directory for the RAG agent.")
        logger.debug(f"Example: Create a file in the user's personal_data directory, e.g., my_notes.txt")

if __name__ == "__main__":
    # This is a simplified way to handle PYTHONPATH for script execution
    # It assumes anp_open_sdk is one level up from backend_py
    import sys
    from pathlib import Path
    # Add the parent directory of backend_py (mcp-chat-extension) to sys.path
    # This helps Python find anp_open_sdk if it's structured like mcp-chat-extension/anp_open_sdk
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Now try to import again, in case it failed at module level
    try:
        from app.services.user_service import create_user_with_anp
        from app.models.schemas import UserCreate
    except ImportError as e:
        logger.debug(f"Failed to import necessary modules. Ensure anp_open_sdk is in your PYTHONPATH or installed. Error: {e}")
        logger.debug(f"Current sys.path: {sys.path}")
        sys.exit(1)
        
    main()