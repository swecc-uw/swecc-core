"""Tests for slash_commands/reading.py"""

import pytest
from slash_commands.reading import Chapter, ReadingGroupConfig, format_reading_pages


class TestChapter:
    """Test suite for Chapter dataclass."""

    def test_chapter_str(self):
        """Test Chapter string representation."""
        # Arrange
        chapter = Chapter(number=1, subtitle="Test Chapter", length=42)

        # Act
        result = str(chapter)

        # Assert
        assert result == "**Chapter 1.** *Test Chapter*"

    def test_chapter_with_pages(self):
        """Test Chapter with_pages method."""
        # Arrange
        chapter = Chapter(number=1, subtitle="Test Chapter", length=42)

        # Act
        result = chapter.with_pages()

        # Assert
        assert result == "**Chapter 1.** *Test Chapter* (42 pages)"


class TestReadingGroupConfig:
    """Test suite for ReadingGroupConfig."""

    def test_config_defaults(self):
        """Test ReadingGroupConfig default values."""
        # Arrange & Act
        config = ReadingGroupConfig()

        # Assert
        assert config.message_title == "📚 Weekly Reading Assignment 📚"
        assert len(config.chapters) == 12
        assert len(config.chapter_schedule) == 10
        assert config.chapters[0].number == 1
        assert config.chapters[0].subtitle == "Reliable, Scalable, and Maintainable Applications"


class TestFormatReadingPages:
    """Test suite for format_reading_pages function."""

    def test_format_reading_pages_single_chapter(self):
        """Test formatting single chapter."""
        # Arrange
        chapter_indices = [0]

        # Act
        chapters, total_pages = format_reading_pages(chapter_indices)

        # Assert
        assert len(chapters) == 1
        assert "Chapter 1" in chapters[0]
        assert "24 pages" in chapters[0]
        assert total_pages == 24

    def test_format_reading_pages_multiple_chapters(self):
        """Test formatting multiple chapters."""
        # Arrange
        chapter_indices = [0, 1]

        # Act
        chapters, total_pages = format_reading_pages(chapter_indices)

        # Assert
        assert len(chapters) == 2
        assert "Chapter 1" in chapters[0]
        assert "Chapter 2" in chapters[1]
        assert total_pages == 66  # 24 + 42
