from datetime import timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from members.models import User
from PIL import Image as PILImage
from rest_framework.test import APIClient, APITestCase

from .models import Component, Image, Page, Text

# ============================================================================
# Model Tests - Page
# ============================================================================


class PageModelTests(TestCase):
    """Test Page model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_page_creation_with_required_fields(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

        # Assert
        self.assertEqual(page.title, "Test Page")
        self.assertEqual(page.created_by, self.user)
        self.assertIsNotNone(page.created)
        self.assertIsNotNone(page.last_updated)
        self.assertFalse(page.is_pubished)  # Note: typo in model field name

    def test_page_default_is_published_false(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

        # Assert
        self.assertFalse(page.is_pubished)

    def test_page_can_be_published(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
            is_pubished=True,
        )

        # Assert
        self.assertTrue(page.is_pubished)

    def test_page_last_updated_default(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

        # Assert
        self.assertIsNotNone(page.last_updated)
        # last_updated should be close to created (within a second)
        time_diff = abs((page.last_updated - page.created).total_seconds())
        self.assertLess(time_diff, 1.0)

    def test_page_str_representation(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

        # Assert
        expected_str = f"{page.title} - {page.created_by} - {page.last_updated}"
        self.assertEqual(str(page), expected_str)

    def test_page_protect_on_user_delete(self):
        # Arrange
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

        # Act & Assert - should raise ProtectedError
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_page_title_max_length(self):
        # Arrange & Act
        long_title = "A" * 100
        page = Page.objects.create(
            title=long_title,
            created_by=self.user,
        )

        # Assert
        self.assertEqual(len(page.title), 100)

    def test_multiple_pages_per_user(self):
        # Arrange & Act
        page1 = Page.objects.create(
            title="Page 1",
            created_by=self.user,
        )
        page2 = Page.objects.create(
            title="Page 2",
            created_by=self.user,
        )

        # Assert
        user_pages = Page.objects.filter(created_by=self.user)
        self.assertEqual(user_pages.count(), 2)
        self.assertIn(page1, user_pages)
        self.assertIn(page2, user_pages)

    def test_page_last_updated_index(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

        # Assert - verify the index exists (PostgreSQL-specific, skip for SQLite)
        from django.db import connection

        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'contentManage_page'
                    AND indexdef LIKE '%last_updated%'
                """
                )
                indexes = cursor.fetchall()
                self.assertTrue(len(indexes) > 0, "Index on last_updated should exist")
        else:
            # Skip this test for non-PostgreSQL databases
            self.skipTest("This test is PostgreSQL-specific")


# ============================================================================
# Model Tests - Component
# ============================================================================


class ComponentModelTests(TestCase):
    """Test Component model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )

    def test_component_creation_with_required_fields(self):
        # Arrange & Act
        component = Component.objects.create(
            parent_page=self.page,
            title="Test Component",
            created_by=self.user,
        )

        # Assert
        self.assertEqual(component.parent_page, self.page)
        self.assertEqual(component.title, "Test Component")
        self.assertEqual(component.created_by, self.user)
        self.assertIsNotNone(component.created)

    def test_component_cascade_delete_with_page(self):
        # Arrange
        component = Component.objects.create(
            parent_page=self.page,
            title="Test Component",
            created_by=self.user,
        )
        component_id = component.component_id

        # Act
        self.page.delete()

        # Assert
        self.assertFalse(Component.objects.filter(component_id=component_id).exists())

    def test_component_protect_on_user_delete(self):
        # Arrange
        component = Component.objects.create(
            parent_page=self.page,
            title="Test Component",
            created_by=self.user,
        )

        # Act & Assert
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_component_str_representation(self):
        # Arrange & Act
        component = Component.objects.create(
            parent_page=self.page,
            title="Test Component",
            created_by=self.user,
        )

        # Assert
        expected_str = f"{component.title} - {component.created} - {component.created_by}"
        self.assertEqual(str(component), expected_str)

    def test_multiple_components_per_page(self):
        # Arrange & Act
        component1 = Component.objects.create(
            parent_page=self.page,
            title="Component 1",
            created_by=self.user,
        )
        component2 = Component.objects.create(
            parent_page=self.page,
            title="Component 2",
            created_by=self.user,
        )

        # Assert
        page_components = Component.objects.filter(parent_page=self.page)
        self.assertEqual(page_components.count(), 2)
        self.assertIn(component1, page_components)
        self.assertIn(component2, page_components)


# ============================================================================
# Model Tests - Image
# ============================================================================


class ImageModelTests(TestCase):
    """Test Image model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )
        self.component = Component.objects.create(
            parent_page=self.page,
            title="Test Component",
            created_by=self.user,
        )

    def _create_test_image(self):
        """Helper to create a test image file"""
        file = BytesIO()
        image = PILImage.new("RGB", (100, 100), color="red")
        image.save(file, "PNG")
        file.seek(0)
        return SimpleUploadedFile("test_image.png", file.read(), content_type="image/png")

    def test_image_creation_with_required_fields(self):
        # Arrange
        image_file = self._create_test_image()

        # Act
        image = Image.objects.create(
            title="Test Image",
            parent_component=self.component,
            image=image_file,
        )

        # Assert
        self.assertEqual(image.title, "Test Image")
        self.assertEqual(image.parent_component, self.component)
        self.assertIsNotNone(image.image)

    def test_image_cascade_delete_with_component(self):
        # Arrange
        image_file = self._create_test_image()
        image = Image.objects.create(
            title="Test Image",
            parent_component=self.component,
            image=image_file,
        )
        image_id = image.image_id

        # Act
        self.component.delete()

        # Assert
        self.assertFalse(Image.objects.filter(image_id=image_id).exists())

    def test_image_str_representation(self):
        # Arrange
        image_file = self._create_test_image()
        image = Image.objects.create(
            title="Test Image",
            parent_component=self.component,
            image=image_file,
        )

        # Assert
        expected_str = f"{image.image_id}: {image.title} - {image.image.url}"
        self.assertEqual(str(image), expected_str)

    def test_image_related_name(self):
        # Arrange
        image_file = self._create_test_image()
        image = Image.objects.create(
            title="Test Image",
            parent_component=self.component,
            image=image_file,
        )

        # Assert
        self.assertIn(image, self.component.image_field.all())

    def test_multiple_images_per_component(self):
        # Arrange & Act
        image1 = Image.objects.create(
            title="Image 1",
            parent_component=self.component,
            image=self._create_test_image(),
        )
        image2 = Image.objects.create(
            title="Image 2",
            parent_component=self.component,
            image=self._create_test_image(),
        )

        # Assert
        component_images = self.component.image_field.all()
        self.assertEqual(component_images.count(), 2)
        self.assertIn(image1, component_images)
        self.assertIn(image2, component_images)


# ============================================================================
# Model Tests - Text
# ============================================================================


class TextModelTests(TestCase):
    """Test Text model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )
        self.component = Component.objects.create(
            parent_page=self.page,
            title="Test Component",
            created_by=self.user,
        )

    def test_text_creation_with_required_fields(self):
        # Arrange & Act
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
        )

        # Assert
        self.assertEqual(text.parent_component, self.component)
        self.assertEqual(text.title, "Test Text")
        self.assertIsNone(text.short_line)
        self.assertIsNone(text.pargraph)  # Note: typo in model field name
        self.assertIsNone(text.url)

    def test_text_creation_with_all_fields(self):
        # Arrange & Act
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
            short_line="Short description",
            pargraph="This is a longer paragraph with more details.",
            url="https://example.com",
        )

        # Assert
        self.assertEqual(text.title, "Test Text")
        self.assertEqual(text.short_line, "Short description")
        self.assertEqual(text.pargraph, "This is a longer paragraph with more details.")
        self.assertEqual(text.url, "https://example.com")

    def test_text_cascade_delete_with_component(self):
        # Arrange
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
        )
        text_id = text.id

        # Act
        self.component.delete()

        # Assert
        self.assertFalse(Text.objects.filter(id=text_id).exists())

    def test_text_str_representation(self):
        # Arrange & Act
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
        )

        # Assert
        expected_str = f"{text.title}, belongs to  {text.parent_component.title}"
        self.assertEqual(str(text), expected_str)

    def test_text_related_name(self):
        # Arrange
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
        )

        # Assert
        self.assertIn(text, self.component.text_field.all())

    def test_multiple_texts_per_component(self):
        # Arrange & Act
        text1 = Text.objects.create(
            parent_component=self.component,
            title="Text 1",
        )
        text2 = Text.objects.create(
            parent_component=self.component,
            title="Text 2",
        )

        # Assert
        component_texts = self.component.text_field.all()
        self.assertEqual(component_texts.count(), 2)
        self.assertIn(text1, component_texts)
        self.assertIn(text2, component_texts)

    def test_text_url_validation(self):
        # Arrange & Act
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
            url="https://example.com/path?query=value",
        )

        # Assert
        self.assertEqual(text.url, "https://example.com/path?query=value")

    def test_text_optional_fields_can_be_blank(self):
        # Arrange & Act
        text = Text.objects.create(
            parent_component=self.component,
            title="Test Text",
            short_line="",
            pargraph="",
            url="",
        )

        # Assert
        self.assertEqual(text.short_line, "")
        self.assertEqual(text.pargraph, "")
        self.assertEqual(text.url, "")

    def test_text_title_max_length(self):
        # Arrange & Act
        long_title = "A" * 25
        text = Text.objects.create(
            parent_component=self.component,
            title=long_title,
        )

        # Assert
        self.assertEqual(len(text.title), 25)

    def test_text_short_line_max_length(self):
        # Arrange & Act
        long_short_line = "B" * 25
        text = Text.objects.create(
            parent_component=self.component,
            title="Test",
            short_line=long_short_line,
        )

        # Assert
        self.assertEqual(len(text.short_line), 25)


# ============================================================================
# Integration Tests - Model Relationships
# ============================================================================


class ModelRelationshipTests(TestCase):
    """Test relationships between models"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_full_content_hierarchy(self):
        # Arrange & Act
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )
        component = Component.objects.create(
            parent_page=page,
            title="Test Component",
            created_by=self.user,
        )
        text = Text.objects.create(
            parent_component=component,
            title="Test Text",
        )

        # Assert
        self.assertEqual(text.parent_component, component)
        self.assertEqual(component.parent_page, page)
        self.assertEqual(page.created_by, self.user)

    def test_page_deletion_cascades_to_components_and_children(self):
        # Arrange
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )
        component = Component.objects.create(
            parent_page=page,
            title="Test Component",
            created_by=self.user,
        )
        text = Text.objects.create(
            parent_component=component,
            title="Test Text",
        )
        text_id = text.id
        component_id = component.component_id

        # Act
        page.delete()

        # Assert
        self.assertFalse(Component.objects.filter(component_id=component_id).exists())
        self.assertFalse(Text.objects.filter(id=text_id).exists())

    def test_component_with_multiple_content_types(self):
        # Arrange
        page = Page.objects.create(
            title="Test Page",
            created_by=self.user,
        )
        component = Component.objects.create(
            parent_page=page,
            title="Test Component",
            created_by=self.user,
        )

        # Act
        text1 = Text.objects.create(
            parent_component=component,
            title="Text 1",
        )
        text2 = Text.objects.create(
            parent_component=component,
            title="Text 2",
        )

        # Create test image
        file = BytesIO()
        image = PILImage.new("RGB", (100, 100), color="red")
        image.save(file, "PNG")
        file.seek(0)
        image_file = SimpleUploadedFile("test.png", file.read(), content_type="image/png")

        image1 = Image.objects.create(
            title="Image 1",
            parent_component=component,
            image=image_file,
        )

        # Assert
        self.assertEqual(component.text_field.count(), 2)
        self.assertEqual(component.image_field.count(), 1)
        self.assertIn(text1, component.text_field.all())
        self.assertIn(text2, component.text_field.all())
        self.assertIn(image1, component.image_field.all())
