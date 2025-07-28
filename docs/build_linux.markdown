# Сборка исполняемого файла под Linux (Ubuntu/Debian)

Эти инструкции описывают процесс сборки исполняемого файла для приложения **DOCX to Markdown Converter Pro** под Linux (на примере Ubuntu/Debian) с использованием `pyinstaller`.

## Требования

- **Python 3.8+**: Установлен по умолчанию в большинстве дистрибутивов или через `apt`.
- **Pandoc 2.14+**: Установите через пакетный менеджер или с [pandoc.org](https://pandoc.org/installing.html).
- **ImageMagick**: Установите для конвертации EMF в PNG.
- **Ghostscript**: Необходим для обработки EMF-файлов. Установите через пакетный менеджер.
- **Git** (опционально): Для клонирования репозитория.

## Установка зависимостей

1. Установите системные зависимости:
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip pandoc imagemagick ghostscript
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

- Выполните `./dist/Converter` для запуска приложения.
- Убедитесь, что Pandoc, ImageMagick и Ghostscript доступны в системе.

## Устранение неполадок

- **Ошибка "Pandoc не найден"**: Проверьте установку Pandoc (`pandoc --version`).
- **Ошибка обработки EMF-файлов**: Убедитесь, что ImageMagick (`magick -version`) и Ghostscript (`gs --version`) поддерживают EMF. Отредактируйте `/etc/ImageMagick-6/policy.xml`, убрав ограничения для `EMF`:
  ```xml
  <policy domain="coder" rights="read|write" pattern="EMF" />
  ```
- **PyQt5 не работает**: Установите совместимую версию: `pip install PyQt5>=5.15`.
- **Ошибка сборки**: Используйте виртуальное окружение для изоляции зависимостей.

## Дополнительно

- Для проверки без сборки:
  ```bash
  python3 -m src.main
  ```
- Для отладки удалите флаг `--onefile`, чтобы получить папку с зависимостями.