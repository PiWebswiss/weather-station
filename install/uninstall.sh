#!/bin/bash

# Formatting stuff
bold=$(tput bold)
normal=$(tput sgr0)
red=$(tput setaf 1)
green=$(tput setaf 2)

APPNAME="inkypi"
LEGACY_APPNAME="e-inkpi"
INSTALL_PATH="/usr/local/$APPNAME"
LEGACY_INSTALL_PATH="/usr/local/$LEGACY_APPNAME"
BINPATH="/usr/local/bin"
SERVICE_NAMES=("$APPNAME.service" "$LEGACY_APPNAME.service")
SERVICE_FILES=("/etc/systemd/system/$APPNAME.service" "/etc/systemd/system/$LEGACY_APPNAME.service")
INSTALL_PATHS=("$INSTALL_PATH" "$LEGACY_INSTALL_PATH")
BIN_FILES=("$BINPATH/$APPNAME" "$BINPATH/$LEGACY_APPNAME")
RUNTIME_DIRS=("/run/$APPNAME" "/run/$LEGACY_APPNAME")

echo_success() {
  echo -e "$1 [\e[32m\xE2\x9C\x94\e[0m]"
}

echo_override() {
  echo -e "\r$1"
}

echo_header() {
  echo -e "${bold}$1${normal}"
}

echo_error() {
  echo -e "${red}$1${normal} [\e[31m\xE2\x9C\x98\e[0m]\n"
}

check_permissions() {
  # Ensure the script is run with sudo
  if [ "$EUID" -ne 0 ]; then
    echo_error "ERROR: Uninstallation requires root privileges. Please run it with sudo."
    exit 1
  fi
}

stop_services() {
  echo "Stopping installed services"
  for service_name in "${SERVICE_NAMES[@]}"; do
    if /usr/bin/systemctl is-active --quiet "$service_name"; then
      /usr/bin/systemctl stop "$service_name"
      echo_success "\tStopped $service_name."
    else
      echo_success "\t$service_name is not running."
    fi
  done
}

disable_services() {
  echo "Disabling installed services"
  local daemon_reload_required=0

  for index in "${!SERVICE_NAMES[@]}"; do
    local service_name="${SERVICE_NAMES[$index]}"
    local service_file="${SERVICE_FILES[$index]}"

    if [ -f "$service_file" ]; then
      /usr/bin/systemctl disable "$service_name" > /dev/null 2>&1 || true
      rm -f "$service_file"
      daemon_reload_required=1
      echo_success "\tDisabled and removed $service_name."
    else
      echo_success "\t$service_name service file does not exist."
    fi
  done

  if [ "$daemon_reload_required" -eq 1 ]; then
    /usr/bin/systemctl daemon-reload
    /usr/bin/systemctl reset-failed > /dev/null 2>&1 || true
  fi
}

remove_generated_config_files() {
  local install_root="$1"
  local config_dir="$install_root/src/config"
  local resolved_install_root
  local resolved_config_dir

  if [ ! -d "$config_dir" ]; then
    echo_success "\tConfig directory does not exist in $install_root."
    return
  fi

  resolved_install_root=$(realpath -m "$install_root")
  resolved_config_dir=$(realpath -m "$config_dir")

  if [[ "$resolved_config_dir" != "$resolved_install_root"* ]]; then
    echo_success "\tSkipping config cleanup for $config_dir because it resolves outside the install directory."
    return
  fi

  for config_name in device.json plugins.json; do
    local config_file="$config_dir/$config_name"
    if [ -f "$config_file" ]; then
      rm -f "$config_file"
      echo_success "\tRemoved $config_file."
    else
      echo_success "\t$config_file does not exist."
    fi
  done
}

remove_files() {
  echo "Removing application files"

  for install_root in "${INSTALL_PATHS[@]}"; do
    remove_generated_config_files "$install_root"
    if [ -d "$install_root" ]; then
      rm -rf "$install_root"
      echo_success "\tInstallation directory $install_root removed."
    else
      echo_success "\tInstallation directory $install_root does not exist."
    fi
  done

  for bin_file in "${BIN_FILES[@]}"; do
    if [ -f "$bin_file" ]; then
      rm -f "$bin_file"
      echo_success "\tExecutable $bin_file removed."
    else
      echo_success "\tExecutable $bin_file does not exist."
    fi
  done

  for runtime_dir in "${RUNTIME_DIRS[@]}"; do
    if [ -d "$runtime_dir" ]; then
      rm -rf "$runtime_dir"
      echo_success "\tRuntime directory $runtime_dir removed."
    else
      echo_success "\tRuntime directory $runtime_dir does not exist."
    fi
  done
}

confirm_uninstall() {
  echo -e "${bold}Are you sure you want to uninstall $APPNAME? This will also remove legacy $LEGACY_APPNAME files if they exist. (y/N): ${normal}"
  read -r confirmation
  if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
    echo_error "Uninstallation cancelled."
    exit 1
  fi
}

remove_firewall() {
  echo "Removing firewall rules..."
  if command -v ufw &>/dev/null; then
    ufw --force reset > /dev/null 2>&1
    ufw --force disable > /dev/null 2>&1
    echo_success "\tFirewall rules removed and ufw disabled."
  else
    echo_success "\tufw not installed, nothing to remove."
  fi
}

check_permissions
confirm_uninstall
stop_services
disable_services
remove_files
remove_firewall

echo ""
echo_success "Uninstallation complete."
echo_header "All components of $APPNAME have been removed from this system."
