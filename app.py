import warnings
warnings.filterwarnings("default", category=DeprecationWarning)

# Import modules
import config
from ui.app import initialize_ui, run_ui

def main():
    # Initialize the UI
    initialize_ui()
    
    # Run the UI
    run_ui()

if __name__ == '__main__':
    main()