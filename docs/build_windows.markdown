# Сборка исполняемого файла под Windows 10/11

Эти инструкции описывают процесс сборки исполняемого файла для приложения **DOCX to Markdown Converter Pro** под Windows 10 или 11 с использованием `pyinstaller`.

## Требования

- **Python 3.8+**: Скачайте и установите с [python.org](https://www.python.org/downloads/). Убедитесь, что Python добавлен в системную переменную PATH.
- **Pandoc 2.14+**: Скачайте MSI-установщик с [pandoc.org](https://pandoc.org/installing.html) и установите. Добавьте Pandoc в PATH (например, `C:\Program Files\Pandoc`).
- **ImageMagick**: Скачайте бинарный файл для Windows с [imagemagick.org](https://imagemagick.org/script/download.php). Установите и добавьте в PATH (например, `C:\Program Files\ImageMagick`).
- **Ghostscript**: Необходим для обработки EMF-файлов. Установите с [ghostscript.com](https://ghostscript.com/releases/) и добавьте в PATH.
- **Git** (опционально): Для клонирования репозитория, установите с [git-scm.com](https://git-scm.com/downloads).

## Установка зависимостей

1. Клонируйте репозиторий (или распакуйте архив проекта):
   ```bash
   git clone https://github.com/ShukinSN/Converter-DOCX-vs-MD.git
   cd Converter-DOCX-vs-MD
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
   pyinstaller --onefile --windowed --name Converter --add-data "src;src" --icon=src\icons.ico src/main.py
   ```

   - `--onefile`: Создаёт единый исполняемый файл.
   - `--windowed`: Запускает приложение без консоли (для GUI).
   - `--name Converter`: Задаёт имя исполняемого файла.
   - `--add-data "src;src"`: Включает папку `src` с модулями проекта.
   - `--icon=src\icons.ico`: Указывает иконку приложения.

2. Альтернативно используйте файл спецификации:
   ```bash
   pyinstaller main.spec
   ```

3. После успешной сборки найдите исполняемый файл `Converter.exe` в папке `dist/`.

## Запуск

- Дважды щёлкните по `Converter.exe` в папке `dist/`, чтобы запустить приложение.
- Убедитесь, что Pandoc, ImageMagick и Ghostscript доступны в PATH.

## Устранение неполадок

- **Ошибка "Pandoc не найден"**: Проверьте, что Pandoc установлен и добавлен в PATH (`pandoc --version`).
- **Ошибка обработки EMF-файлов**: Убедитесь, что ImageMagick (`magick -version`) и Ghostscript (`gs --version`) установлены.
- **PyQt5 не работает**: Установите совместимую версию: `pip install PyQt5>=5.15`.
- **Файл слишком большой**: Исполняемый файл может быть большим из-за зависимостей. Для уменьшения размера используйте виртуальное окружение или удалите флаг `--onefile` для отладки.

## Дополнительно

- Для проверки работоспособности без сборки выполните:
  ```bash
  python -m src.main
  ```
- Для отладки удалите флаг `--onefile` в команде `pyinstaller`, чтобы получить папку с зависимостями.