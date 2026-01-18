# Universal installer & alias injectorimport os
import sys
import shutil
import subprocess
import platform

# --- Configuration ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(REPO_ROOT, "contexts")
CONFIG_FILE = os.path.join(REPO_ROOT, "config", "aider.conf.yml")

# Mapping short keywords to file lists
DOMAIN_MAP = {
    "gpu": ["gpu_builder.md", "gpu_optim.md"],
    "net": ["net_kernel.md"],
    "ml": ["ml_systems.md"],
    "soft": ["soft_arch.md"]
}

def print_status(msg, status="INFO"):
    print(f"[{status}] {msg}")

def install_aider_pipx():
    """Installs pipx and aider if not present."""
    if not shutil.which("pipx"):
        print_status("pipx not found. Attempting to install...", "WARN")
        # Crude attempt to install pipx, user might need to do this manually on some systems
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "pipx"])
            subprocess.check_call([sys.executable, "-m", "pipx", "ensurepath"])
        except subprocess.CalledProcessError:
            print_status("Failed to install pipx. Please install it manually.", "ERROR")
            sys.exit(1)
    
    if not shutil.which("aider"):
        print_status("Installing aider-chat via pipx...", "ACTION")
        subprocess.check_call(["pipx", "install", "aider-chat"])
    else:
        print_status("Aider is already installed.", "OK")

def get_shell_config():
    """Determines the shell config file and syntax based on OS."""
    system = platform.system()
    
    if system == "Windows":
        # PowerShell Profile
        try:
            profile = subprocess.check_output(["powershell", "-NoProfile", "echo $PROFILE"], text=True).strip()
            return "powershell", profile
        except:
            return "powershell", None # Handle error gracefully
            
    else:
        # Linux/WSL (Bash/Zsh)
        shell = os.environ.get("SHELL", "/bin/bash")
        if "zsh" in shell:
            return "zsh", os.path.expanduser("~/.zshrc")
        else:
            return "bash", os.path.expanduser("~/.bashrc")

def generate_bash_function():
    """Generates the Bash/Zsh function string."""
    # We embed the Python logic directly into the alias to resolve paths dynamically
    # but for speed, we will generate a shell function that calls this script or constructs the command.
    # To keep it simple and fast, we will write a Shell function that maps the keys.
    
    # We hardcode the paths in the shell function for the specific machine this is installed on.
    
    func_body = f"""
# --- Sys-Workbench Mix ---
sys-mix() {{
    local cmd="aider --config \\"{CONFIG_FILE}\\""
    local has_args=false

    for arg in "$@"; do
        case "$arg" in
"""
    for key, files in DOMAIN_MAP.items():
        files_paths = [os.path.join(CONTEXT_DIR, f) for f in files]
        # --read adds the file to chat context
        read_flags = " ".join([f'--read "{p}"' for p in files_paths])
        func_body += f"""            "{key}")
                cmd="$cmd {read_flags}"
                has_args=true
                ;;
"""
    
    func_body += """            *)
                echo "Unknown domain: $arg"
                echo "Available: gpu, net, ml, soft"
                return 1
                ;;
        esac
    done

    if [ "$has_args" = true ]; then
        echo "Starting Sys-Workbench with: $@"
        eval "$cmd"
    else
        echo "Usage: sys-mix [gpu|net|ml|soft] ..."
    fi
}
"""
    return func_body

def generate_powershell_function():
    """Generates the PowerShell function string."""
    
    func_body = f"""
# --- Sys-Workbench Mix ---
function sys-mix {{
    param(
        [Parameter(ValueFromRemainingArguments=$true)]
        [String[]]$Domains
    )

    $aiderCmd = "aider --config '{CONFIG_FILE}'"
    $hasArgs = $false

    foreach ($domain in $Domains) {{
        switch ($domain) {{
"""
    for key, files in DOMAIN_MAP.items():
        files_paths = [os.path.join(CONTEXT_DIR, f) for f in files]
        read_flags = " ".join([f"--read '{p}'" for p in files_paths])
        func_body += f"""            "{key}" {{
                $aiderCmd += " {read_flags}"
                $hasArgs = $true
            }}
"""

    func_body += """            Default {
                Write-Host "Unknown domain: $domain" -ForegroundColor Red
                Write-Host "Available: gpu, net, ml, soft"
                return
            }
        }
    }

    if ($hasArgs) {
        Write-Host "Starting Sys-Workbench..." -ForegroundColor Green
        Invoke-Expression $aiderCmd
    } else {
        Write-Host "Usage: sys-mix [gpu|net|ml|soft] ..."
    }
}}
"""
    return func_body

def install_alias():
    shell_type, config_path = get_shell_config()
    
    if not config_path or not os.path.exists(os.path.dirname(config_path)):
        # For Windows, directory might not exist
        if shell_type == "powershell":
             os.makedirs(os.path.dirname(config_path), exist_ok=True)
             if not os.path.exists(config_path):
                 with open(config_path, 'w') as f: f.write("")
        else:
            print_status(f"Could not locate shell config file: {config_path}", "ERROR")
            return

    print_status(f"Detected {shell_type}. Injecting 'sys-mix' into {config_path}...", "ACTION")

    if shell_type == "powershell":
        func_code = generate_powershell_function()
    else:
        func_code = generate_bash_function()

    # Check if already installed
    with open(config_path, "r") as f:
        content = f.read()
    
    if "# --- Sys-Workbench Mix ---" in content:
        print_status("sys-mix function already exists. Please remove it manually to update.", "WARN")
    else:
        with open(config_path, "a") as f:
            f.write("\n" + func_code + "\n")
        print_status("Injection successful!", "SUCCESS")
        if shell_type == "powershell":
             print_status(f"Run '. {config_path}' to refresh.", "INFO")
        else:
             print_status(f"Run 'source {config_path}' to refresh.", "INFO")

if __name__ == "__main__":
    print_status(f"Initializing Sys-Workbench at {REPO_ROOT}...", "INFO")
    install_aider_pipx()
    install_alias()
    print_status("Setup Complete. Use 'sys-mix gpu net' to start.", "SUCCESS")