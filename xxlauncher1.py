import os
import sys
import logging
import threading
import subprocess
import re
from time import time

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.logger import Logger

import minecraft_launcher_lib
from plyer import filechooser

logging.basicConfig(
    filename='xxlauncher.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)

MINECRAFT_DIR = os.path.join(os.path.expanduser("~"), ".xxlauncher")
MINECRAFT_LOG = os.path.join(MINECRAFT_DIR, "game_output.log")

def get_java_version(java_path):
    try:
        result = subprocess.run([java_path, '-version'], capture_output=True, text=True, timeout=5)
        output = result.stderr + result.stdout
        match = re.search(r'version "(\d+)(?:\.(\d+))?', output)
        if match:
            major = match.group(1)
            if major == '1':
                return 8
            else:
                return int(major)
    except:
        return 0

def is_java_compatible(java_path, minecraft_version):
    java_ver = get_java_version(java_path)
    if java_ver == 0:
        return False, "Не удалось определить версию Java. Проверьте путь."
    try:
        major = int(minecraft_version.split('.')[1])
    except:
        return True, ""
    if major >= 18:
        required = 17
        required_name = "17"
    elif major == 17:
        required = 16
        required_name = "16 или 17"
    else:
        required = 8
        required_name = "8"
    if java_ver < required:
        return False, f"Для Minecraft {minecraft_version} требуется Java {required_name}, а у вас Java {java_ver}."
    return True, ""

class XXLauncherApp(App):
    def build(self):
        Window.size = (500, 450)
        self.title = "XXLauncher"
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)

        layout.add_widget(Label(text="Ник игрока:", size_hint_y=0.1))
        self.nick_input = TextInput(text="Player", multiline=False, size_hint_y=0.1)
        layout.add_widget(self.nick_input)

        layout.add_widget(Label(text="Версия Minecraft:", size_hint_y=0.1))
        self.version_spinner = Spinner(text='Выберите версию', values=[], size_hint_y=0.1)
        layout.add_widget(self.version_spinner)

        layout.add_widget(Label(text="Путь к Java:", size_hint_y=0.1))
        java_path_layout = BoxLayout(orientation='horizontal', size_hint_y=0.1)
        self.java_path_input = TextInput(text=self.find_java(), multiline=False, size_hint_x=0.7)
        java_path_layout.add_widget(self.java_path_input)
        self.java_choose_btn = Button(text="Обзор...", size_hint_x=0.3)
        self.java_choose_btn.bind(on_press=self.choose_java)
        java_path_layout.add_widget(self.java_choose_btn)
        layout.add_widget(java_path_layout)

        self.launch_btn = Button(text="Запустить Minecraft", size_hint_y=0.1)
        self.launch_btn.bind(on_press=self.launch_minecraft)
        layout.add_widget(self.launch_btn)

        self.status_label = Label(text="Готов к запуску", size_hint_y=0.2, color=(0,1,0,1))
        layout.add_widget(self.status_label)

        threading.Thread(target=self.load_versions, daemon=True).start()
        return layout

    def find_java(self):
        if os.name == 'nt':
            patterns = [
                r"C:\Program Files\Java\jre-*\bin\java.exe",
                r"C:\Program Files\Java\jdk-*\bin\java.exe",
                r"C:\Program Files (x86)\Java\jre-*\bin\java.exe",
                r"C:\Program Files (x86)\Java\jdk-*\bin\java.exe",
            ]
            for pattern in patterns:
                import glob
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
        else:
            import shutil
            java_path = shutil.which("java")
            if java_path:
                return java_path
        return "java"

    def choose_java(self, instance):
        try:
            file_path = filechooser.open_file(title="Выберите исполняемый файл Java", filters=["*.exe", "*"])
            if file_path:
                self.java_path_input.text = file_path[0]
        except Exception as e:
            Logger.error(f"Ошибка выбора файла: {e}")

    def load_versions(self):
        try:
            versions = minecraft_launcher_lib.utils.get_version_list()
            version_list = [v["id"] for v in versions if v["type"] in ["release", "snapshot"]]
            self.update_version_spinner(version_list)
        except Exception as e:
            logging.exception("Не удалось загрузить версии")
            self.update_status(f"Ошибка загрузки версий: {e}", error=True)

    @mainthread
    def update_version_spinner(self, versions):
        self.version_spinner.values = versions
        if versions:
            self.version_spinner.text = versions[0]

    def launch_minecraft(self, instance):
        self.launch_btn.disabled = True
        self.update_status("Подготовка...")
        threading.Thread(target=self._run_minecraft, daemon=True).start()

    @mainthread
    def update_status(self, message, error=False):
        self.status_label.text = message
        self.status_label.color = (1, 0, 0, 1) if error else (0, 1, 0, 1)

    def _run_minecraft(self):
        logging.debug("Поток запущен")
        nick = self.nick_input.text.strip()
        version = self.version_spinner.text
        java_path = self.java_path_input.text.strip()

        if not nick:
            self.update_status("Введите ник!", error=True)
            self.launch_btn.disabled = False
            return
        if version == "Выберите версию" or not version:
            self.update_status("Выберите версию!", error=True)
            self.launch_btn.disabled = False
            return
        if not java_path or not os.path.exists(java_path):
            self.update_status("Укажите корректный путь к Java!", error=True)
            self.launch_btn.disabled = False
            return

        compatible, msg = is_java_compatible(java_path, version)
        if not compatible:
            self.update_status(msg, error=True)
            self.launch_btn.disabled = False
            return

        try:
            os.makedirs(MINECRAFT_DIR, exist_ok=True)

            installed = minecraft_launcher_lib.utils.get_installed_versions(MINECRAFT_DIR)
            installed_ids = [v["id"] for v in installed]

            if version not in installed_ids:
                self.update_status(f"Установка {version}...")
                minecraft_launcher_lib.install.install_minecraft_version(version, MINECRAFT_DIR)

            self.update_status("Запуск Minecraft...")

            # Важно: уменьшаем память до 1 ГБ (для 32-битной Java может потребоваться 768M или 512M)
            options = {
                "username": nick,
                "uuid": "",
                "token": "",
                "executablePath": java_path,
                "jvmArguments": ["-Xmx1G"],   # <- ИЗМЕНЕНО с 2G на 1G
            }
            command = minecraft_launcher_lib.command.get_minecraft_command(
                version=version,
                minecraft_directory=MINECRAFT_DIR,
                options=options
            )

            with open(MINECRAFT_LOG, 'w', encoding='utf-8') as log_file:
                process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, text=True)
                return_code = process.wait()

            if return_code != 0:
                with open(MINECRAFT_LOG, 'r', encoding='utf-8') as log_file:
                    last_lines = log_file.readlines()[-20:]
                error_output = ''.join(last_lines)
                logging.error(f"Ошибка запуска (код {return_code}):\n{error_output}")
                self.update_status(f"Ошибка (код {return_code}). Проверьте {MINECRAFT_LOG}", error=True)
            else:
                self.update_status("Игра завершена.")

        except Exception as e:
            logging.exception("Критическая ошибка")
            self.update_status(f"Ошибка: {e}", error=True)
        finally:
            self.launch_btn.disabled = False

if __name__ == "__main__":
    XXLauncherApp().run()