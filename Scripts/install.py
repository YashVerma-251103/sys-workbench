import os
import sys
import shutil
import subprocess
import platform
import json
from pathlib import Path

# --- Configuration ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(REPO_ROOT, "contexts")
CONFIG_FILE = os.path.join(REPO_ROOT, "config", "aider.conf.yml")
ENV_NAME = "sys-workbench-safe"

# --- Visuals ---
COLORS = {
    "HEADER": "\033[95m", "BLUE": "\033[94m", "CYAN": "\033[96m",
    "GREEN": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m",
    "END": "\033[0m", "BOLD": "\033[1m"
}

def log(msg, type="INFO"):
    prefix = {
        "INFO": f"{COLORS['BLUE']}[INFO]{COLORS['END']}",
        "SUCCESS": f"{COLORS['GREEN']}[SUCCESS]{COLORS['END']}",
        "WARN": f"{COLORS['WARN']}[WARN]{COLORS['END']}",
        "ERROR": f"{COLORS['FAIL']}[ERROR]{COLORS['END']}",
        "ACTION": f"{COLORS['CYAN']}[ACTION]{COLORS['END']}",
    }
    print(f"{prefix.get(type, '[?]')} {msg}")

def ask_user(question, default="yes"):
    """Asks the user for permission."""
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    prompt = " [Y/n] " if default == "yes" else " [y/N] "
    while True:
        sys.stdout.write(f"{COLORS['WARN']}{question}{prompt}{COLORS['END']}")
        choice = input().lower().strip()
        if choice == "": return True if default == "yes" else False
        if choice in valid: return valid[choice]

def run_cmd(cmd, check=True):
    print(f"{COLORS['BOLD']}> {' '.join(cmd)}{COLORS['END']}")
    return subprocess.run(cmd, check=check, text=True)

# --- Step 1: Python Environment ---
def get_conda_path():
    return shutil.which("conda")

def setup_python_env():
    log("Checking Python compatibility...", "INFO")
    
    if os.environ.get("CONDA_DEFAULT_ENV") == ENV_NAME:
        return sys.executable

    major, minor = sys.version_info[:2]
    is_windows = platform.system() == "Windows"
    conda_exe = get_conda_path()
    
    if not conda_exe:
        return sys.executable

    # Check for existing env
    try:
        envs_json = subprocess.check_output([conda_exe, "env", "list", "--json"], text=True)
        env_paths = json.loads(envs_json).get("envs", [])
        target_path = next((p for p in env_paths if os.path.basename(os.path.normpath(p)) == ENV_NAME), None)
    except:
        target_path = None

    if target_path:
        log(f"Found existing environment: {target_path}", "SUCCESS")
    else:
        if ask_user(f"Create isolated environment '{ENV_NAME}' (Recommended)?"):
            run_cmd([conda_exe, "create", "-n", ENV_NAME, "python=3.11", "-y"])
            # Re-fetch path
            envs_json = subprocess.check_output([conda_exe, "env", "list", "--json"], text=True)
            env_paths = json.loads(envs_json).get("envs", [])
            target_path = next((p for p in env_paths if os.path.basename(os.path.normpath(p)) == ENV_NAME), None)
        else:
            log("Using system python (Not recommended for Windows).", "WARN")
            return sys.executable

    if is_windows:
        return os.path.join(target_path, "python.exe")
    else:
        return os.path.join(target_path, "bin", "python")

# --- Step 2: Install Tools ---
def install_pipx():
    try:
        subprocess.check_call([sys.executable, "-m", "pipx", "--version"], stdout=subprocess.DEVNULL)
    except:
        log("Pipx not found.", "WARN")
        if ask_user("Install pipx now?"):
            run_cmd([sys.executable, "-m", "pip", "install", "--user", "pipx"])

def install_aider(target_python):
    try:
        res = subprocess.run([sys.executable, "-m", "pipx", "list"], capture_output=True, text=True)
        if "aider-chat" in res.stdout:
            log("Aider is already installed.", "SUCCESS")
            return
    except: pass

    if ask_user(f"Install Aider using {os.path.basename(target_python)}?"):
        run_cmd([sys.executable, "-m", "pipx", "install", "aider-chat", "--python", target_python, "--force"])

# --- Step 3: Find Executable ---
def find_absolute_aider_path():
    log("Locating aider executable...", "INFO")
    candidates = [
        os.path.join(os.path.expanduser("~"), ".local", "bin", "aider.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python", "Scripts", "aider.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python", f"Python{sys.version_info.major}{sys.version_info.minor}", "Scripts", "aider.exe")
    ]
    
    # Check candidates
    for path in candidates:
        if os.path.exists(path):
            log(f"Found Executable: {path}", "SUCCESS")
            return path
            
    which = shutil.which("aider")
    if which: return which
    return None

# --- Step 4: Profile Injection ---
def generate_powershell_function(exe_path):
    return f"""
# --- Sys-Workbench Mix ---
function sys-mix {{
    param(
        [Parameter(ValueFromRemainingArguments=$true)]
        [String[]]$Domains
    )
    $aiderExe = "{exe_path}"
    $aiderCmd = "& '$aiderExe' --config '{CONFIG_FILE}'"
    $hasArgs = $false

    foreach ($domain in $Domains) {{
        switch ($domain) {{
            {_get_ps_cases()}
            Default {{ Write-Host "Unknown: $domain"; return }}
        }}
    }}

    if ($hasArgs) {{
        Write-Host "Starting Sys-Workbench..." -ForegroundColor Green
        Invoke-Expression $aiderCmd
    }} else {{
        Write-Host "Usage: sys-mix [gpu|net|ml|soft]"
    }}
}}
"""

def generate_bash_function(exe_path):
    # For WSL/Linux
    return f"""
# --- Sys-Workbench Mix ---
sys-mix() {{
    local cmd="'{exe_path}' --config \\"{CONFIG_FILE}\\""
    local has_args=false
    for arg in "$@"; do
        case "$arg" in
            {_get_bash_cases()}
            *) echo "Unknown domain: $arg"; return 1 ;;
        esac
    done
    if [ "$has_args" = true ]; then
        echo "Starting Sys-Workbench..."; eval "$cmd"
    else
        echo "Usage: sys-mix [gpu|net|ml|soft]"
    fi
}}
"""

def _get_ps_cases():
    cases = ""
    for key, files in {
        "gpu": ["gpu_builder.md", "gpu_optim.md"],
        "net": ["net_kernel.md"],
        "ml": ["ml_systems.md"],
        "soft": ["soft_arch.md"]
    }.items():
        paths = [os.path.join(CONTEXT_DIR, f) for f in files]
        flags = " ".join([f"--read '{p}'" for p in paths])
        cases += f'"{key}" {{ $aiderCmd += " {flags}"; $hasArgs = $true }}\n            '
    return cases

def _get_bash_cases():
    cases = ""
    for key, files in {
        "gpu": ["gpu_builder.md", "gpu_optim.md"],
        "net": ["net_kernel.md"],
        "ml": ["ml_systems.md"],
        "soft": ["soft_arch.md"]
    }.items():
        paths = [os.path.join(CONTEXT_DIR, f) for f in files]
        flags = " ".join([f'--read "{p}"' for p in paths])
        cases += f'"{key}") cmd="$cmd {flags}"; has_args=true ;;\n            '
    return cases

def install_alias(exe_path):
    if platform.system() == "Windows":
        try:
            profile = subprocess.check_output(["powershell", "-NoProfile", "echo $PROFILE"], text=True).strip()
            func_code = generate_powershell_function(exe_path)
        except: return
    else:
        # Linux/WSL
        shell = os.environ.get("SHELL", "/bin/bash")
        profile = os.path.expanduser("~/.zshrc") if "zsh" in shell else os.path.expanduser("~/.bashrc")
        func_code = generate_bash_function(exe_path)

    if not os.path.exists(os.path.dirname(profile)):
        os.makedirs(os.path.dirname(profile), exist_ok=True)

    if ask_user(f"Add 'sys-mix' alias to {os.path.basename(profile)}?"):
        with open(profile, "a") as f:
            f.write("\n" + func_code + "\n")
        log("Profile updated.", "SUCCESS")

if __name__ == "__main__":
    print(f"{COLORS['HEADER']}--- Sys-Workbench Clean Install ---{COLORS['END']}")
    
    target_py = setup_python_env()
    install_pipx()
    install_aider(target_py)
    
    exe_path = find_absolute_aider_path()
    if exe_path:
        install_alias(exe_path)
        print(f"\n{COLORS['GREEN']}INSTALLATION COMPLETE.{COLORS['END']}")
        print("Run this command to refresh your terminal:")
        if platform.system() == "Windows":
             print(f"  {COLORS['BOLD']}. $PROFILE{COLORS['END']}")
        else:
             print(f"  {COLORS['BOLD']}source ~/.bashrc{COLORS['END']}")
    else:
        log("CRITICAL: Aider installed but executable not found.", "ERROR")