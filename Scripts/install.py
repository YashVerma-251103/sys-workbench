import os
import sys
import shutil
import subprocess
import platform
import json
import re

# --- Configuration ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(REPO_ROOT, "contexts")
CONFIG_FILE = os.path.join(REPO_ROOT, "config", "aider.conf.yml")
ENV_FILE = os.path.join(REPO_ROOT, ".env")
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
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    prompt = " [Y/n] " if default == "yes" else " [y/N] "
    while True:
        sys.stdout.write(f"{COLORS['WARN']}{question}{prompt}{COLORS['END']}")
        choice = input().lower().strip()
        if choice == "": return True if default == "yes" else False
        if choice in valid: return valid[choice]

# --- Feature: Interactive Configuration ---
def configure_token_limits():
    log("Running Configuration Wizard...", "INFO")
    if not os.path.exists(CONFIG_FILE): return

    with open(CONFIG_FILE, 'r') as f: content = f.read()

    # Chat History Limit
    if "max-chat-history-tokens" not in content:
        print(f"\n{COLORS['BOLD']}--- [Decision] Context Window ---{COLORS['END']}")
        if ask_user("Enable High Context (20k tokens)?", default="yes"):
            tok = "20000"
        else:
            tok = "5000"
        content += f"\nmax-chat-history-tokens: {tok}"
        
        # Repo Map
        if ask_user("Enable Large Repo Map (2048 tokens)?", default="yes"):
            map_tok = "2048"
        else:
            map_tok = "1024"
        content += f"\nmap-tokens: {map_tok}\n"

        with open(CONFIG_FILE, 'w') as f: f.write(content)
        log("Configuration updated.", "SUCCESS")

# --- Feature: API Key Setup ---
def setup_api_keys():
    log("Checking API Keys...", "INFO")
    if not os.path.exists(ENV_FILE):
        log("No .env file found. Creating template...", "WARN")
        with open(ENV_FILE, "w") as f:
            f.write("DEEPSEEK_API_KEY=\nANTHROPIC_API_KEY=\nOPENAI_API_KEY=\n")
        log(f"Created {ENV_FILE}. Please edit it.", "ACTION")
    
    # Update .gitignore
    gitignore = os.path.join(REPO_ROOT, ".gitignore")
    if os.path.exists(gitignore):
        with open(gitignore, "r") as f:
            if ".env" not in f.read():
                with open(gitignore, "a") as af: af.write("\n.env\n")

# --- Step 1: Python Env ---
def setup_python_env():
    if os.environ.get("CONDA_DEFAULT_ENV") == ENV_NAME: return sys.executable
    conda = shutil.which("conda")
    if not conda: return sys.executable
    
    try:
        out = subprocess.check_output([conda, "env", "list", "--json"], text=True)
        envs = json.loads(out).get("envs", [])
        target = next((p for p in envs if os.path.basename(os.path.normpath(p)) == ENV_NAME), None)
    except: target = None

    if not target:
        if ask_user(f"Create conda env '{ENV_NAME}'?"):
            subprocess.run([conda, "create", "-n", ENV_NAME, "python=3.11", "-y"], check=True)
            return setup_python_env() # Recurse to find path
        return sys.executable

    return os.path.join(target, "python.exe") if platform.system() == "Windows" else os.path.join(target, "bin", "python")

# --- Step 2: Install Tools ---
def install_aider(target_python):
    try:
        subprocess.check_call([sys.executable, "-m", "pipx", "--version"], stdout=subprocess.DEVNULL)
    except:
        if ask_user("Install pipx?"):
            subprocess.run([sys.executable, "-m", "pip", "install", "--user", "pipx"], check=True)
            subprocess.run([sys.executable, "-m", "pipx", "ensurepath"], check=False)

    try:
        res = subprocess.run([sys.executable, "-m", "pipx", "list"], capture_output=True, text=True)
        if "aider-chat" in res.stdout: return
    except: pass

    if ask_user(f"Install Aider?"):
        subprocess.run([sys.executable, "-m", "pipx", "install", "aider-chat", "--python", target_python, "--force"], check=True)

# --- Step 3: Find Aider ---
def find_aider_executable():
    which = shutil.which("aider")
    if which: return which
    
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".local", "bin", "aider.exe"),
        os.path.join(home, "AppData", "Roaming", "Python", "Scripts", "aider.exe"),
        os.path.join(home, "AppData", "Local", "Programs", "Python", "Scripts", "aider.exe")
    ]
    try:
        base = subprocess.check_output([sys.executable, "-m", "site", "--user-base"], text=True).strip()
        candidates.append(os.path.join(base, "bin", "aider.exe"))
        candidates.append(os.path.join(base, "Scripts", "aider.exe"))
    except: pass

    for p in candidates:
        if os.path.exists(p): return p
    return None

# --- Step 4: Shell Generators (FIXED) ---
def generate_powershell_function(exe_path):
    # FIX: Use @() array for arguments instead of string splitting
    return f"""
function sys-mix {{
    $exe = "{exe_path}"
    $config = "{CONFIG_FILE}"
    $envPath = "{ENV_FILE}"

    # Safety Check
    try {{
        $branch = git rev-parse --abbrev-ref HEAD 2>$null
        if ($branch -match "^(main|master)$") {{
            Write-Host "[SAFETY LOCK] Switch to a feature branch first." -ForegroundColor Red
            return
        }}
    }} catch {{}}

    # Base Arguments
    $aiderArgs = @("--config", $config, "--env-file", $envPath)
    
    # Parse User Input
    $domains = @()
    foreach ($arg in $args) {{
        if ($arg.StartsWith("-")) {{ $aiderArgs += $arg }}
        else {{ $domains += $arg }}
    }}

    $sorted = $domains | Sort-Object | Get-Unique
    foreach ($d in $sorted) {{
        switch ($d) {{
            {_get_ps_cases()}
            Default {{ Write-Host "Unknown domain: $d" -ForegroundColor Red }}
        }}
    }}

    Write-Host "Starting Aider..." -ForegroundColor Green
    & $exe $aiderArgs
}}
"""

def generate_bash_function(exe_path):
    # FIX: Use Bash Arrays properly
    p_conf = CONFIG_FILE.replace(os.sep, '/')
    p_env = ENV_FILE.replace(os.sep, '/')
    p_exe = exe_path.replace(os.sep, '/')
    
    return f"""
sys-mix() {{
    local exe="{p_exe}"
    
    # Safety Check
    local branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [[ "$branch" == "main" || "$branch" == "master" ]]; then
        echo -e "\\033[31m[SAFETY LOCK] Switch to a feature branch first.\\033[0m"
        return 1
    fi

    local args=("--config" "{p_conf}" "--env-file" "{p_env}")
    local domains=()

    for arg in "$@"; do
        if [[ "$arg" == -* ]]; then
            args+=("$arg")
        else
            domains+=("$arg")
        fi
    done

    IFS=$'\\n' sorted_domains=($(sort <<<"${{domains[*]}}")); unset IFS
    
    for d in "${{sorted_domains[@]}}"; do
        case "$d" in
            {_get_bash_cases()}
            *) echo "Unknown: $d"; return 1 ;;
        esac
    done
    
    echo "Starting Aider..."
    "$exe" "${{args[@]}}"
}}
"""

def _get_ps_cases():
    cases = ""
    # Map domains to files
    domain_map = {
        "gpu": ["gpu_builder.md", "gpu_optim.md"],
        "net": ["net_kernel.md"],
        "ml": ["ml_systems.md"],
        "soft": ["soft_arch.md"]
    }
    
    for key, files in domain_map.items():
        # FIX: Add to array, DO NOT QUOTE THE PATHS HERE
        # PowerShell handles the quoting of array elements automatically
        paths_code = ""
        for f in files:
            p = os.path.join(CONTEXT_DIR, f)
            paths_code += f'$aiderArgs += "--read"; $aiderArgs += "{p}"; '
            
        cases += f'"{key}" {{ {paths_code} }}\n            '
    return cases

def _get_bash_cases():
    cases = ""
    domain_map = {
        "gpu": ["gpu_builder.md", "gpu_optim.md"],
        "net": ["net_kernel.md"],
        "ml": ["ml_systems.md"],
        "soft": ["soft_arch.md"]
    }
    
    for key, files in domain_map.items():
        # FIX: Bash array appending
        paths_code = ""
        for f in files:
            p = os.path.join(CONTEXT_DIR, f).replace(os.sep, '/')
            paths_code += f'args+=("--read" "{p}"); '
            
        cases += f'"{key}") {paths_code} ;;\n            '
    return cases

if __name__ == "__main__":
    print(f"{COLORS['HEADER']}--- Sys-Workbench Final Install ---{COLORS['END']}")
    setup_api_keys()
    configure_token_limits()
    
    if not shutil.which("git"):
        log("Git not found.", "ERROR"); sys.exit(1)

    target_py = setup_python_env()
    install_aider(target_py)
    
    exe_path = find_aider_executable()
    if not exe_path:
        log("Aider not found.", "ERROR")
    else:
        # Install Alias
        if platform.system() == "Windows":
            try:
                profile = subprocess.check_output(["powershell", "-NoProfile", "echo $PROFILE"], text=True).strip()
                code = generate_powershell_function(exe_path)
                if not os.path.exists(os.path.dirname(profile)): os.makedirs(os.path.dirname(profile))
                
                with open(profile, "a") as f: f.write("\n" + code + "\n")
                print(f"\n{COLORS['GREEN']}INSTALLED.{COLORS['END']}")
                print(f"Run: {COLORS['BOLD']}. $PROFILE{COLORS['END']}")
            except: log("Failed to update Profile.", "ERROR")
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            rc = os.path.expanduser("~/.zshrc") if "zsh" in shell else os.path.expanduser("~/.bashrc")
            code = generate_bash_function(exe_path)
            with open(rc, "a") as f: f.write("\n" + code + "\n")
            print(f"\n{COLORS['GREEN']}INSTALLED.{COLORS['END']}")
            print(f"Run: {COLORS['BOLD']}source {rc}{COLORS['END']}")