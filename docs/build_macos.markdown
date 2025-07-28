# Сборка исполняемого файла под macOS

Эти инструкции описывают процесс сборки исполняемого файла для приложения **DOCX to Markdown Converter Pro** под macOS с использованием `pyinstaller`.

## Требования

- **Python 3.8+**: Установите через [python.org](https://www.python.org/downloads/) или Homebrew (`brew install python`).
- **Pandoc 2.14+**: Установите через Homebrew (`brew install pandoc`) или с [pandoc.org](https://pandoc.org/installing.html).
- **ImageMagick**: Установите через Homebrew (`brew install imagemagick`).
- **Ghostscript**: Необходим для обработки EMF-файлов. Установите через Homebrew (`brew install ghostscript`).
- **Git** (опционально): Для клонирования репозитория (`brew install git`).

## Установка зависимостей

1. Установите системные зависимости:
   ```bash
   brew install python pandoc imagemagick ghostscript
   ```

2. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/ShukinSN/Converter-DOCX-vs-MD.git
   cd Converter-DOCX-vs-MD
   ```

3. Установите Python-зависимости:
   ```bash
   pip install -r requirements.txt
   ```

4. Установите `pyinstaller`:
   ```bash
   pip install pyinstaller
   ```

## Сборка исполняемого файла

1. Выполните команду для сборки:
   ```bash
   pyinstaller --onefile --windowed --name Converter --add-data "src:src" src/main.py
   ```

   - `--onefile`: Создаёт единый исполняемый файл.
   - `--windowed`: Запускает приложение без консоли (для GUI).
   - `--name Converter`: Задаёт имя исполняемого файла.
   - `--add-data "src:src"`: Включает папку `src` с модулями проекта.

2. Альтернативно используйте файл спецификации:
   ```bash
   pyinstaller main.spec
   ```

3. После успешной сборки найдите исполняемый файл `Converter` в папке `dist/`.

## Запуск

- Выполните `./dist/Converter` или дважды щёлкните по файлу в Finder для запуска.
- Убедитесь, что Pandoc, ImageMagick и Ghostscript доступны в системе.

## Устранение неполадок

- **Ошибка "Pandoc не найден"**: Проверьте установку Pandoc (`pandoc --version`).
- **Ошибка обработки EMF-файлов**: Убедитесь, что ImageMagick (`magick -version`) и Ghostscript (`gs --version`) установлены.
- **PyQt5 не работает**: Установите совместимую версию: `pip install PyQt5>=5.15`.
- **Ошибка "Недоверенное приложение"**: Разрешите запуск в настройках безопасности macOS или используйте:
  ```bash
  xattr -d com.apple.quarantine dist/docx2md
  ```

## Дополнительно

- Для проверки без сборки:
  ```bash
  python3 -m src.main
  ```
- Для отладки удалите флаг `--onefile`, чтобы получить папку с зависимостями.