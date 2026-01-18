# A2A Multi-Agent system package

# Import client module from the installed a2a-sdk package
try:
    # Import from the installed a2a-sdk package
    import sys
    import importlib.util
    
    # Find the installed a2a package in site-packages
    for path in sys.path:
        if 'site-packages' in path:
            a2a_client_path = f"{path}/a2a/client"
            spec = importlib.util.find_spec("a2a.client")
            if spec is not None:
                # Import the client module from the installed package
                from a2a import client
                break
    else:
        # Fallback: try direct import
        import a2a.client as client
except ImportError as e:
    print(f"Warning: Could not import a2a.client: {e}")
    client = None
