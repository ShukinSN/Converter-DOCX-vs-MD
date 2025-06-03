# Сборка исполняемого файла под Windows 10/11

Эти инструкции описывают процесс сборки исполняемого файла для приложения **DOCX to Markdown Converter Pro** под Windows 10 или 11 с использованием `pyinstaller`.

## Требования

- **Python 3.8+**: Скачайте и установите с [python.org](https://www.python.org/downloads/). Убедитесь, что Python добавлен в системную переменную PATH.
- **Pandoc 2.14+**: Скачайте MSI-установщик с [pandoc.org](https://pandoc.org/installing.html) и установите. Добавьте Pandoc в PATH (например, `C:\Program Files\Pandoc`).
- **ImageMagick**: Скачайте бинарный файл для Windows с [imagemagick.org](https://imagemagick.org/script/download.php). Установите и добавьте в PATH (например, `C:\Program Files\ImageMagick`).
- **Git** (опционально): Для клонирования репозитория, установите с [git-scm.com](https://git-scm.com/downloads).

## Установка зависимостей

1. Клонируйте репозиторий (или распакуйте архив проекта):
   ```bash
   git clone https://github.com/your-username/docx-to-markdown-converter.git
   cd docx-to-markdown-converter
   ```

2. Установите Python-зависимости из `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

3. Установите `pyinstaller` для сборки:
   ```bash
   pip install pyinstaller
   ```

## Сборка исполняемого файла

1. Выполните команду для сборки с помощью `pyinstaller`:
   ```bash
   pyinstaller --onefile --windowed --name docx2md --add-data "src;src" src/main.py
   ```

   - `--onefile`: Создаёт единый исполняемый файл.
   - `--windowed`: Запускает приложение без консоли (для GUI).
   - `--name docx2md`: Задаёт имя исполняемого файла.
   - `--add-data "src;src"`: Включает папку `src` с модулями проекта.

2. После успешной сборки найдите исполняемый файл `docx2md.exe` в папке `dist/`.

## Запуск

- Дважды щёлкните по `docx2md.exe` в папке `dist/`, чтобы запустить приложение.
- Убедитесь, что Pandoc и ImageMagick доступны в PATH, иначе приложение может не работать корректно.

## Устранение неполадок

- **Ошибка "Pandoc не найден"**: Проверьте, что Pandoc установлен и добавлен в PATH. Выполните `pandoc --version` в командной строке для проверки.
- **Ошибка обработки EMF-файлов**: Убедитесь, что ImageMagick установлен и поддерживает EMF. Проверьте `magick -version`.
- **PyQt5 не работает**: Установите совместимую версию: `pip install PyQt5>=5.15`.
- **Файл слишком большой**: Исполняемый файл может быть большим из-за включения всех зависимостей. Для уменьшения размера рассмотрите использование виртуального окружения или исключение ненужных библиотек.

## Дополнительно

- Для проверки работоспособности без сборки выполните:
  ```bash
  python -m src.main
  ```
- Если требуется отладка, удалите флаг `--onefile` в команде `pyinstaller`, чтобы получить папку с зависимостями для анализа.