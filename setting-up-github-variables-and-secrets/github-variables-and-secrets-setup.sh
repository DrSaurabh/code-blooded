#!/bin/bash

# script to read in a config.yaml file and create or update GitHub variables and secrets as per the configuration defined therein.

## Prerequisites:
# - yq (for YAML parsing)
# - jq (for JSON parsing)
# - gh CLI (GitHub CLI)
# - A GitHub token with access to the repo and the necessary permissions.


## How to use this script:
# 1. Create a config file named "github-variables-and-secrets-config.yaml" with the template below.
    # authentication:
        # ORG: "myorg"
        # REPO: "myrepo"
        # GITHUB_TOKEN: "ghp_****"

    # variables:
        # A: "value for A"
        # AA: "value for AA"

    # secrets:
        # B: "secret value for B"
        # BB: "secret value for BB"

# 2 Make sure this script is executable:
#    chmod +x github-variables-and-secrets-setup.sh 

# 3 Run the script:
#    ./github-variables-and-secrets-setup.sh


# Do note that variable names are case-sensitive in GitHub, so they will be stored as such, while
# secret names are always uppercased by GitHub.

CONFIG_FILE="github-variables-and-secrets-config.yaml"

# Global display truncation width (applies to preview tables and value displays)
TRUNCATE_WIDTH=40


authenticate() {
    # Load authentication and config from YAML
    GITHUB_TOKEN=$(yq -r '.authentication.GITHUB_TOKEN' "$CONFIG_FILE")
    ORG=$(yq -r '.authentication.ORG' "$CONFIG_FILE")
    REPO=$(yq -r '.authentication.REPO' "$CONFIG_FILE")
    echo "$GITHUB_TOKEN" | gh auth login --with-token >/dev/null 2>&1 || true
}

get_column_width() {
    # Function to calculate column width (with minimum + 2 spaces padding)
    local section="$1"
    local min_width=12

    local max_len
    max_len=$(yq -r ".$section | to_entries[].key" "$CONFIG_FILE" | awk '{print length}' | sort -nr | head -n1)

    if [ -z "$max_len" ]; then
        echo "$min_width"
    else
        if [ "$max_len" -lt "$min_width" ]; then
            echo $((min_width + 2))
        else
            echo $((max_len + 2))
        fi
    fi
}

truncate_display() {
    local str="$1" width="$2"
    local len=${#str}
    if [ "$len" -gt "$width" ]; then
        echo "${str:0:$((width-3))}..."
    else
        echo "$str"
    fi
}

print_config_summary() {
    # Function to pretty-print variables and secrets for confirmation
    echo
    echo "Setting up GitHub variables and secrets for"
    echo "$ORG/$REPO"
    echo
    echo "The following variables and secrets will be set up or updated:"
    echo "============================="
    echo

    # Variables
    local var_width
    var_width=$(get_column_width "variables")
    echo "VARIABLES"
    printf -- "%-${var_width}s-+-%s\n" "$(printf '%.0s-' $(seq 1 $var_width))" "--------------------------------"
    yq -r '.variables | to_entries[] | "\(.key)|\(.value)"' "$CONFIG_FILE" \
        | while IFS="|" read -r name value; do
            printf "%-${var_width}s | %s\n" "$(truncate_display "$name" "$var_width")" "$(truncate_display "$value" $TRUNCATE_WIDTH)"
        done
    echo

    # Secrets
    local sec_width
    sec_width=$(get_column_width "secrets")
    echo "SECRETS"
    printf -- "%-${sec_width}s-+-%s\n" "$(printf '%.0s-' $(seq 1 $sec_width))" "--------------------------------"
    yq -r '.secrets | to_entries[] | "\(.key)|\(.value)"' "$CONFIG_FILE" \
        | while IFS="|" read -r name value; do
            printf "%-${sec_width}s | %s\n" "$(truncate_display "$name" "$sec_width")" "$(truncate_display "$value" $TRUNCATE_WIDTH)"
        done
    echo
}

sanity_check() {
    # Function for sanity check
    while true; do
        echo "Do you want to [A]ccept, [R]eload, or [Q]uit?"
        read -rp "Your choice: " choice
        case "$choice" in
            [Aa]* )
                echo "Accepted. Continuing..."
                break
                ;;
            [Rr]* )
                clear
                echo "Reloading configuration..."
                authenticate
                print_config_summary
                ;;
            [Qq]* )
                echo "Quitting. No changes made."
                exit 0
                ;;
            * )
                echo "Invalid choice. Please enter A, R, or Q."
                ;;
        esac
    done
}

create_github_variable() {
    local variableName="$1"
    local variableValue="$2"

    local status="Created"
    local prevValue=""
    local timestamp
    timestamp=$(date +"%H:%M %p [ %d-%m-%Y ]")

    # Try to fetch existing variable
    local details
    if details=$(gh api repos/"$ORG"/"$REPO"/actions/variables/"$variableName" 2>/dev/null); then
        # Variable exists
        prevValue=$(echo "$details" | jq -r '.value')
        # Update
        gh api \
            --method PATCH \
            repos/"$ORG"/"$REPO"/actions/variables/"$variableName" \
            -f name="$variableName" \
            -f value="$variableValue" >/dev/null
        status="Updated"
    else
        # Not found → create
        gh api \
            --method POST \
            repos/"$ORG"/"$REPO"/actions/variables \
            -f name="$variableName" \
            -f value="$variableValue" >/dev/null
    fi



    local name_disp value_disp prev_disp
    name_disp=$(truncate_display "$variableName" "$COL_WIDTH")
    value_disp=$(truncate_display "$variableValue" "$CURR_WIDTH")
    prev_disp=$(truncate_display "$prevValue" "$PREV_WIDTH")

    printf "%-${COL_WIDTH}s | %-${CURR_WIDTH}s | %-${PREV_WIDTH}s | %-${STATUS_WIDTH}s | %s\n" \
        "$name_disp" "$value_disp" "$prev_disp" "$status" "$timestamp"
}

process_variables() {
    echo
    echo "Processing variables..."
    echo

    # --- Column width settings ---
    NAME_MIN=12
    NAME_MAX=30

    VAL_MIN=15
    VAL_MAX=40

    STATUS_WIDTH=10

    # --- Calculate NAME width ---
    COL_WIDTH=$(yq -r '.variables | to_entries[].key' "$CONFIG_FILE" \
        | awk '{print length}' | sort -nr | head -n1)
    COL_WIDTH=$(( COL_WIDTH < NAME_MIN ? NAME_MIN : COL_WIDTH + 2 ))
    [ "$COL_WIDTH" -gt "$NAME_MAX" ] && COL_WIDTH=$NAME_MAX

    # --- Calculate VALUE widths (CURRENT + PREV) ---
    CURR_WIDTH=$(yq -r '.variables | to_entries[].value' "$CONFIG_FILE" \
        | awk '{print length}' | sort -nr | head -n1)
    CURR_WIDTH=$(( CURR_WIDTH < VAL_MIN ? VAL_MIN : CURR_WIDTH + 2 ))
    [ "$CURR_WIDTH" -gt "$VAL_MAX" ] && CURR_WIDTH=$VAL_MAX

    PREV_WIDTH=$CURR_WIDTH   # keep aligned

    # --- Header ---
    printf "%-${COL_WIDTH}s | %-${CURR_WIDTH}s | %-${PREV_WIDTH}s | %-${STATUS_WIDTH}s | %s\n" \
        "NAME" "CURRENT VALUE" "PREV VALUE" "STATUS" "TIMESTAMP"

    # --- Divider ---
    printf -- "%-${COL_WIDTH}s-+-%-${CURR_WIDTH}s-+-%-${PREV_WIDTH}s-+-%-${STATUS_WIDTH}s-+-%s\n" \
        "$(printf '%.0s-' $(seq 1 $COL_WIDTH))" \
        "$(printf '%.0s-' $(seq 1 $CURR_WIDTH))" \
        "$(printf '%.0s-' $(seq 1 $PREV_WIDTH))" \
        "$(printf '%.0s-' $(seq 1 $STATUS_WIDTH))" \
        "--------------------------------"

    # --- Print variables ---
    yq -r '.variables | to_entries[] | "\(.key)=\(.value)"' "$CONFIG_FILE" \
        | while IFS='=' read -r key value; do
                        key_disp=$(truncate_display "$key" "$COL_WIDTH")
            value_disp=$(truncate_display "$value" "$CURR_WIDTH")
            create_github_variable "$key" "$value"
        done
    echo
}

create_github_secret() {
    local secretName="$1"     # RAW name from YAML
    local secretValue="$2"    # RAW value from YAML

    local status prevValue timestamp
    timestamp=$(date +"%H:%M %p [ %d-%m-%Y ]")

    # Robust existence check
    if gh api -X GET "repos/$ORG/$REPO/actions/secrets/$secretName" >/dev/null 2>&1; then
        status="Updated"
        prevValue="[ EXISTS ]"
    else
        status="Created"
        prevValue=""
    fi

    # Create or update
    gh secret set "$secretName" -R "$ORG/$REPO" --body "$secretValue" >/dev/null

    # DISPLAY: GitHub always uppercases secret names
    local name_disp value_disp
    name_disp=$(truncate_display "${secretName^^}" "$COL_WIDTH")   # force uppercase
    value_disp=$(truncate_display "$secretValue" "$CURR_WIDTH")

    printf "%-${COL_WIDTH}s | %-${CURR_WIDTH}s | %-${PREV_WIDTH}s | %-${STATUS_WIDTH}s | %s\n" \
        "$name_disp" "$value_disp" "$prevValue" "$status" "$timestamp"
}

process_secrets() {
    echo
    echo "Processing secrets..."
    echo

    # --- Column width settings ---
    NAME_MIN=12
    NAME_MAX=30
    VAL_MIN=15
    VAL_MAX=40
    STATUS_WIDTH=10

    # --- Calculate NAME width ---
    COL_WIDTH=$(yq -r '.secrets | to_entries[].key' "$CONFIG_FILE" \
        | awk '{print length}' | sort -nr | head -n1)
    COL_WIDTH=$(( COL_WIDTH < NAME_MIN ? NAME_MIN : COL_WIDTH + 2 ))
    [ "$COL_WIDTH" -gt "$NAME_MAX" ] && COL_WIDTH=$NAME_MAX

    # --- Calculate VALUE widths (show config value as "Current") ---
    CURR_WIDTH=$(yq -r '.secrets | to_entries[].value' "$CONFIG_FILE" \
        | awk '{print length}' | sort -nr | head -n1)
    CURR_WIDTH=$(( CURR_WIDTH < VAL_MIN ? VAL_MIN : CURR_WIDTH + 2 ))
    [ "$CURR_WIDTH" -gt "$VAL_MAX" ] && CURR_WIDTH=$VAL_MAX

    PREV_WIDTH=$CURR_WIDTH   # align columns

    # --- Header ---
    printf "%-${COL_WIDTH}s | %-${CURR_WIDTH}s | %-${PREV_WIDTH}s | %-${STATUS_WIDTH}s | %s\n" \
        "NAME" "CURRENT VALUE" "PREV VALUE" "STATUS" "TIMESTAMP"

    # --- Divider ---
    printf -- "%-${COL_WIDTH}s-+-%-${CURR_WIDTH}s-+-%-${PREV_WIDTH}s-+-%-${STATUS_WIDTH}s-+-%s\n" \
        "$(printf '%.0s-' $(seq 1 $COL_WIDTH))" \
        "$(printf '%.0s-' $(seq 1 $CURR_WIDTH))" \
        "$(printf '%.0s-' $(seq 1 $PREV_WIDTH))" \
        "$(printf '%.0s-' $(seq 1 $STATUS_WIDTH))" \
        "--------------------------------"

    # --- IMPORTANT: pass RAW key/value to the API function ---
    yq -r '.secrets | to_entries[] | "\(.key)=\(.value)"' "$CONFIG_FILE" \
        | while IFS='=' read -r key value; do
            create_github_secret "$key" "$value"
        done
    echo
}

# Main
authenticate
print_config_summary
sanity_check
process_variables
process_secrets
