# Сборка исполняемого файла под Linux (Ubuntu/Debian)

Эти инструкции описывают процесс сборки исполняемого файла для приложения **DOCX to Markdown Converter Pro** под Linux (на примере Ubuntu/Debian) с использованием `pyinstaller`.

## Требования

- **Python 3.8+**: Установлен по умолчанию в большинстве дистрибутивов или через `apt`.
- **Pandoc 2.14+**: Установите через пакетный менеджер или с [pandoc.org](https://pandoc.org/installing.html).
- **ImageMagick**: Установите для конвертации EMF в PNG.
- **Git** (опционально): Для клонирования репозитория.

## Установка зависимостей

1. Установите системные зависимости:
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip pandoc imagemagick
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
   pyinstaller --onefile --windowed --name docx2md --add-data "src:src" src/main.py
   ```

   - `--onefile`: Создаёт единый исполняемый файл.
   - `--windowed`: Запускает приложение без консоли (для GUI).
   - `--name docx2md`: Задаёт имя исполняемого файла.
   - `--add-data "src:src"`: Включает папку `src` с модулями проекта (используется двоеточие для Linux).

2. После успешной сборки найдите исполняемый файл `docx2md` в папке `dist/`.

## Запуск

- Выполните `./dist/docx2md` для запуска приложения.
- Убедитесь, что Pandoc и ImageMagick доступны в системе.

## Устранение неполадок

- **Ошибка "Pandoc не найден"**: Проверьте установку Pandoc (`pandoc --version`).
- **Ошибка обработки EMF-файлов**: Убедитесь, что ImageMagick поддерживает EMF. Проверьте `magick -version`. Если EMF не работает, отредактируйте `/etc/ImageMagick-6/policy.xml`, убрав ограничения для `EMF`:
  ```xml
  <policy domain="coder" rights="read|write" pattern="EMF" />
  ```
- **PyQt5 не работает**: Установите совместимую версию: `pip install PyQt5>=5.15`.
- **Ошибка сборки**: Убедитесь, что все зависимости установлены корректно, и используйте виртуальное окружение для изоляции.

## Дополнительно

- Для проверки без сборки:
  ```bash
  python3 -m src.main
  ```
- Для отладки удалите флаг `--onefile`, чтобы получить папку с зависимостями.