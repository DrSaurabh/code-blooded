#!/bin/bash
alias reload="echo -n 'reloading '; sleep 0.25; echo -n '.'; sleep 0.25; echo -n '.'; sleep 0.25; echo -n '.'; sleep 0.50; echo; clear && source ~/.bashrc"
# Colors
C='\033[36m'  # Cyan
G='\033[32m'  # Green
Y='\033[33m'  # Yellow
M='\033[35m'  # Magenta
B='\033[1m'   # Bold
D='\033[2m'   # Dim
N='\033[0m'   # Reset

# Display
echo -e "\n${B}━━━${Y} Git Bash${N} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${D}Active GitHub account${N} : ${M}$(cat ~/.ssh/id_github_active 2>/dev/null || echo 'not set')${N}"
echo -e "${D}Name${N}                  : ${M}$(git config --global user.name 2>/dev/null || echo 'not set')${N}"
echo -e "${D}Email${N}                 : ${M}$(git config --global user.email 2>/dev/null || echo 'not set')${N}"
echo -e "${D}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${D} use ${B}${C}ghswitch${N}${D} to change authentication${N}, use ${B}${C}ghfix_remote${N}${D} to reset remote${N}\n"

ghfix_remote() {
  if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    return 0
  fi

  local url
  url=$(git remote get-url origin 2>/dev/null)

  if [[ "$url" == https://github.com/* ]]; then
    local ssh_url
    ssh_url=$(echo "$url" | sed 's|https://github.com/|git@github.com:|')
    git remote set-url origin "$ssh_url"
    echo "Remote fixed → $ssh_url"
  else
    echo "Remote OK → $url"
  fi
}

ghswitch() {

  local current current_name current_email
  current=$(cat ~/.ssh/id_github_active 2>/dev/null)
  current_name=$(git config --global user.name 2>/dev/null)
  current_email=$(git config --global user.email 2>/dev/null)
  echo "Current account : ${current:-none}"
  echo "Name            : ${current_name:-not set}"
  echo "Email           : ${current_email:-not set}"
  echo ""

  echo "Switch to:"
  echo "  [0] work        (Ninja)" # Modify as required
  echo "  [1] personal    (DrSaurabh)" # Modify as required
  echo "  [2] moon        (Neil Armstrong)" # Modify as required
  echo "  [q] Quit without changing anything."

  echo -n "Choice: "
  read -r choice

  case "$choice" in
    0) key="id_work"; name="SaurabhNinja";  email="saurabh@work.com"; acc="Ninja";; # Modify as required
    1) key="id_personal"; name="DrSaurabh";  email="saurabhsawhney@personal.com"; acc="Personal";; # Modify as required
    2) key="id_moon"; name="Neil Armstrong";  email="neil@moon.com"; acc="Moon";; # Modify as required
    q) echo "No changes made."; return 0;;
    *) echo "Invalid choice."; return 1 ;;
  esac

  cp ~/.ssh/"$key" ~/.ssh/id_github
  echo "$acc" > ~/.ssh/id_github_active

  chmod 600 ~/.ssh/id_github
  git config --global user.name  "$name"
  git config --global user.email "$email"

  ssh -T git@github.com 2>&1 | grep -E "Hi|denied"
  echo "Global identity → $name <$email>"

  echo ""
  ghfix_remote
  reload
}
