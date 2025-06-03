# Сборка исполняемого файла под macOS

Эти инструкции описывают процесс сборки исполняемого файла для приложения **DOCX to Markdown Converter Pro** под macOS с использованием `pyinstaller`.

## Требования

- **Python 3.8+**: Установите через [python.org](https://www.python.org/downloads/) или Homebrew (`brew install python`).
- **Pandoc 2.14+**: Установите через Homebrew (`brew install pandoc`) или с [pandoc.org](https://pandoc.org/installing.html).
- **ImageMagick**: Установите через Homebrew (`brew install imagemagick`).
- **Git** (опционально): Для клонирования репозитория (`brew install git`).

## Установка зависимостей

1. Установите системные зависимости:
   ```bash
   brew install python pandoc imagemagick
   ```

2. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/docx-to-markdown-converter.git
   cd docx-to-markdown-converter
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
   pyinstaller --onefile --windowed --name docx2md --add-data "src:src" main.py
   ```

   - `--onefile`: Создаёт единый исполняемый файл.
   - `--windowed`: Запускает приложение без консоли (для GUI).
   - `--name docx2md`: Задаёт имя исполняемого файла.
   - `--add-data "src:src"`: Включает папку `src` с модулями проекта.

2. После успешной сборки найдите исполняемый файл `docx2md` в папке `dist/`.

## Запуск

- Выполните `./dist/docx2md` или дважды щёлкните по файлу в Finder для запуска.
- Убедитесь, что Pandoc и ImageMagick доступны в системе.

## Устранение неполадок

- **Ошибка "Pandoc не найден"**: Проверьте установку Pandoc (`pandoc --version`).
- **Ошибка обработки EMF-файлов**: Убедитесь, что ImageMagick установлен (`magick -version`). Проверьте настройки ImageMagick для поддержки EMF.
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