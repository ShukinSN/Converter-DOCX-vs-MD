# DOCX to Markdown Converter Pro

Приложение на базе PyQt5 для конвертации файлов DOCX в Markdown с современным графическим интерфейсом, функцией предпросмотра и обработкой изображений.

## Описание

Приложение позволяет конвертировать файлы Microsoft Word (DOCX) в Markdown с поддержкой:
- Графического интерфейса с тёмной темой.
- Автоматической обработки изображений (включая конвертацию EMF в PNG).
- Генерации оглавления и исправления ссылок.
- Многопоточной обработки файлов.

## Требования

- **Python 3.8+**: Установите с [python.org](https://www.python.org/downloads/).
- **Pandoc 2.14+**: Установите с [pandoc.org](https://pandoc.org/installing.html).
- **ImageMagick**: Необходим для конвертации EMF в PNG. Установите с [imagemagick.org](https://imagemagick.org/script/download.php).

## Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/docx-to-markdown-converter.git
   cd docx-to-markdown-converter
   ```

2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. (Опционально) Установите инструменты для разработки:
   ```bash
   pip install pyinstaller pytest
   ```

## Запуск без сборки

Для запуска приложения без создания исполняемого файла:
```bash
python -m src.main
```

## Сборка исполняемых файлов

Инструкции для сборки исполняемых файлов для разных операционных систем находятся в папке `docs`:
- [Windows 10/11](https://github.com/ShukinSN/Converter-DOCX-vs-MD/blob/main/docs/build_windows.markdown)
- [Linux (Ubuntu/Debian)](https://github.com/ShukinSN/Converter-DOCX-vs-MD/blob/main/docs/build_linux.markdown)
- [macOS](https://github.com/ShukinSN/Converter-DOCX-vs-MD/blob/main/docs/build_macos.markdown)

## Устранение неполадок

- **Pandoc не найден**: Убедитесь, что Pandoc установлен и добавлен в PATH.
- **Ошибки ImageMagick с EMF**: Проверьте, установлен ли ImageMagick, и разрешите обработку EMF в настройках (`/etc/ImageMagick-6/policy.xml` на Linux).
- **Ошибки PyQt5**: Убедитесь, что установлена совместимая версия (`pip install PyQt5>=5.15`).

## Лицензия

MIT License
