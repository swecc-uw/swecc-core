from unittest.mock import patch

from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from members.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_api_key.models import APIKey

from .models import DiscordChannel
from .serializers import DiscordChannelSerializer


class DiscordChannelModelTests(TestCase):
    """Test DiscordChannel model"""

    def setUp(self):
        """Set up test data"""
        self.channel_data = {
            "channel_id": 123456789,
            "channel_name": "general",
            "category_id": 111111111,
            "channel_type": "TEXT",
            "guild_id": 999999999,
        }

    def test_create_discord_channel(self):
        """Test creating a DiscordChannel instance"""
        # Arrange & Act
        channel = DiscordChannel.objects.create(**self.channel_data)

        # Assert
        self.assertEqual(channel.channel_id, 123456789)
        self.assertEqual(channel.channel_name, "general")
        self.assertEqual(channel.category_id, 111111111)
        self.assertEqual(channel.channel_type, "TEXT")
        self.assertEqual(channel.guild_id, 999999999)

    def test_discord_channel_str_representation(self):
        """Test __str__ method returns channel name"""
        # Arrange
        channel = DiscordChannel.objects.create(**self.channel_data)

        # Act & Assert
        self.assertEqual(str(channel), "general")

    def test_discord_channel_with_null_category(self):
        """Test creating a channel with null category_id"""
        # Arrange
        data = self.channel_data.copy()
        data["category_id"] = None

        # Act
        channel = DiscordChannel.objects.create(**data)

        # Assert
        self.assertIsNone(channel.category_id)
        self.assertEqual(channel.channel_name, "general")

    def test_discord_channel_primary_key(self):
        """Test that channel_id is the primary key"""
        # Arrange & Act
        channel = DiscordChannel.objects.create(**self.channel_data)

        # Assert
        self.assertEqual(channel.pk, channel.channel_id)

    def test_discord_channel_unique_constraint(self):
        """Test that duplicate channel_id raises IntegrityError"""
        # Arrange
        DiscordChannel.objects.create(**self.channel_data)

        # Act & Assert
        with self.assertRaises(IntegrityError):
            DiscordChannel.objects.create(**self.channel_data)

    def test_discord_channel_all_types(self):
        """Test creating channels with all valid channel types"""
        # Arrange
        channel_types = ["TEXT", "VOICE", "CATEGORY", "STAGE", "FORUM"]

        # Act & Assert
        for idx, channel_type in enumerate(channel_types):
            data = self.channel_data.copy()
            data["channel_id"] = 123456789 + idx
            data["channel_type"] = channel_type
            channel = DiscordChannel.objects.create(**data)
            self.assertEqual(channel.channel_type, channel_type)

    def test_discord_channel_max_name_length(self):
        """Test channel name with maximum length"""
        # Arrange
        data = self.channel_data.copy()
        data["channel_name"] = "x" * 255

        # Act
        channel = DiscordChannel.objects.create(**data)

        # Assert
        self.assertEqual(len(channel.channel_name), 255)

    def test_discord_channel_update(self):
        """Test updating a DiscordChannel instance"""
        # Arrange
        channel = DiscordChannel.objects.create(**self.channel_data)

        # Act
        channel.channel_name = "updated-general"
        channel.channel_type = "VOICE"
        channel.save()

        # Assert
        updated_channel = DiscordChannel.objects.get(channel_id=123456789)
        self.assertEqual(updated_channel.channel_name, "updated-general")
        self.assertEqual(updated_channel.channel_type, "VOICE")

    def test_discord_channel_delete(self):
        """Test deleting a DiscordChannel instance"""
        # Arrange
        channel = DiscordChannel.objects.create(**self.channel_data)

        # Act
        channel.delete()

        # Assert
        self.assertFalse(DiscordChannel.objects.filter(channel_id=123456789).exists())

    def test_discord_channel_bulk_create(self):
        """Test bulk creating multiple channels"""
        # Arrange
        channels = [
            DiscordChannel(
                channel_id=i,
                channel_name=f"channel-{i}",
                category_id=111111111,
                channel_type="TEXT",
                guild_id=999999999,
            )
            for i in range(10)
        ]

        # Act
        DiscordChannel.objects.bulk_create(channels)

        # Assert
        self.assertEqual(DiscordChannel.objects.count(), 10)


class DiscordChannelSerializerTests(TestCase):
    """Test DiscordChannelSerializer"""

    def setUp(self):
        """Set up test data"""
        self.channel_data = {
            "channel_id": 123456789,
            "channel_name": "general",
            "category_id": 111111111,
            "channel_type": "TEXT",
            "guild_id": 999999999,
        }

    def test_serializer_with_valid_data(self):
        """Test serializer with valid data"""
        # Arrange
        serializer = DiscordChannelSerializer(data=self.channel_data)

        # Act & Assert
        self.assertTrue(serializer.is_valid())
        channel = serializer.save()
        self.assertEqual(channel.channel_id, 123456789)
        self.assertEqual(channel.channel_name, "general")

    def test_serializer_with_missing_required_field(self):
        """Test serializer with missing required field"""
        # Arrange
        data = self.channel_data.copy()
        del data["channel_type"]
        serializer = DiscordChannelSerializer(data=data)

        # Act & Assert
        self.assertFalse(serializer.is_valid())
        self.assertIn("channel_type", serializer.errors)

    def test_serializer_with_null_category(self):
        """Test serializer with null category_id"""
        # Arrange
        data = self.channel_data.copy()
        data["category_id"] = None
        serializer = DiscordChannelSerializer(data=data)

        # Act & Assert
        self.assertTrue(serializer.is_valid())
        channel = serializer.save()
        self.assertIsNone(channel.category_id)

    def test_serializer_serialization(self):
        """Test serializing a DiscordChannel instance"""
        # Arrange
        channel = DiscordChannel.objects.create(**self.channel_data)
        serializer = DiscordChannelSerializer(channel)

        # Act
        data = serializer.data

        # Assert
        self.assertEqual(data["channel_id"], 123456789)
        self.assertEqual(data["channel_name"], "general")
        self.assertEqual(data["category_id"], 111111111)
        self.assertEqual(data["channel_type"], "TEXT")
        self.assertEqual(data["guild_id"], 999999999)

    def test_serializer_many_channels(self):
        """Test serializing multiple channels"""
        # Arrange
        channels = [
            DiscordChannel.objects.create(
                channel_id=i,
                channel_name=f"channel-{i}",
                category_id=111111111,
                channel_type="TEXT",
                guild_id=999999999,
            )
            for i in range(5)
        ]
        serializer = DiscordChannelSerializer(channels, many=True)

        # Act
        data = serializer.data

        # Assert
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["channel_name"], "channel-0")

    def test_serializer_update(self):
        """Test updating a channel through serializer"""
        # Arrange
        channel = DiscordChannel.objects.create(**self.channel_data)
        update_data = {"channel_name": "updated-general", "channel_type": "VOICE"}
        serializer = DiscordChannelSerializer(channel, data=update_data, partial=True)

        # Act
        self.assertTrue(serializer.is_valid())
        updated_channel = serializer.save()

        # Assert
        self.assertEqual(updated_channel.channel_name, "updated-general")
        self.assertEqual(updated_channel.channel_type, "VOICE")


class DiscordChannelsFuzzedTests(APITestCase):
    def setUp(self):
        api_key, key = APIKey.objects.create_key(name="swecc-bot")
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
        self.url = reverse("discord-channels-sync")

        self.initial_channels = [
            {
                "channel_id": "123456789",
                "channel_name": "general",
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
            {
                "channel_id": "987654321",
                "channel_name": "voice-chat",
                "category_id": "111111111",
                "channel_type": "VOICE",
                "guild_id": "999999999",
            },
            {
                "channel_id": "456789123",
                "channel_name": "announcements",
                "category_id": "222222222",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
            {
                "channel_id": "789123456",
                "channel_name": "gaming",
                "category_id": "333333333",
                "channel_type": "VOICE",
                "guild_id": "999999999",
            },
            {
                "channel_id": "321654987",
                "channel_name": "help-forum",
                "category_id": "444444444",
                "channel_type": "FORUM",
                "guild_id": "999999999",
            },
        ]

        for channel_data in self.initial_channels:
            DiscordChannel.objects.create(**channel_data)

    def test_complex_sync_operation(self):
        updated_channels = [
            # keep one channel unchanged
            self.initial_channels[0],
            # update channel name and type
            {
                "channel_id": "987654321",
                "channel_name": "voice-lounge",  # changed
                "category_id": "111111111",
                "channel_type": "STAGE",  # changed
                "guild_id": "999999999",
            },
            # update channel category
            {
                "channel_id": "456789123",
                "channel_name": "announcements",
                "category_id": "111111111",  # changed
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
            # add new channels
            {
                "channel_id": "111222333",
                "channel_name": "new-text",
                "category_id": "222222222",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
            {
                "channel_id": "444555666",
                "channel_name": "new-voice",
                "category_id": "333333333",
                "channel_type": "VOICE",
                "guild_id": "999999999",
            },
            {
                "channel_id": "777888999",
                "channel_name": "new-forum",
                "category_id": "444444444",
                "channel_type": "FORUM",
                "guild_id": "999999999",
            },
        ]
        # 'gaming' and 'help-forum' will be deleted

        response = self.client.post(self.url, updated_channels, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        changes = response.json()["changes"]
        self.assertEqual(changes["created"], 3)  # 3 new channels
        self.assertEqual(changes["updated"], 2)  # 2 modified channels
        self.assertEqual(changes["deleted"], 2)  # 2 deleted channels

        self.assertEqual(DiscordChannel.objects.count(), 6)

        voice_channel = DiscordChannel.objects.get(channel_id="987654321")
        self.assertEqual(voice_channel.channel_type, "STAGE")
        self.assertEqual(voice_channel.channel_name, "voice-lounge")

        moved_channel = DiscordChannel.objects.get(channel_id="456789123")
        self.assertEqual(moved_channel.category_id, 111111111)

        self.assertFalse(DiscordChannel.objects.filter(channel_id="789123456").exists())
        self.assertFalse(DiscordChannel.objects.filter(channel_id="321654987").exists())

        new_channels = DiscordChannel.objects.filter(
            channel_id__in=["111222333", "444555666", "777888999"]
        )
        self.assertEqual(new_channels.count(), 3)

    def test_idempotency(self):
        response1 = self.client.post(self.url, self.initial_channels, format="json")
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        changes1 = response1.json()["changes"]
        self.assertEqual(changes1["created"], 0)
        self.assertEqual(changes1["updated"], 0)
        self.assertEqual(changes1["deleted"], 0)

        response2 = self.client.post(self.url, self.initial_channels, format="json")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        changes2 = response2.json()["changes"]
        self.assertEqual(changes2["created"], 0)
        self.assertEqual(changes2["updated"], 0)
        self.assertEqual(changes2["deleted"], 0)

    def test_edge_cases(self):
        """Test various edge cases in a single sync operation"""
        edge_case_channels = [
            {
                "channel_id": "111111111",
                "channel_name": "x" * 100,
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
            # channel with same category and name as another
            {
                "channel_id": "222222222",
                "channel_name": "general",  # same name as existing channel
                "category_id": "111111111",  # same category as existing channel
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
            {
                "channel_id": "333333333",
                "channel_name": "a",
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            },
        ]

        response = self.client.post(self.url, edge_case_channels, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            DiscordChannel.objects.filter(
                channel_id__in=["111111111", "222222222", "333333333"]
            ).count(),
            3,
        )

    def test_invalid_cases(self):
        """Test various invalid cases"""

        invalid_channels = [
            # missing channel_type
            {
                "channel_id": "111111111",
                "channel_name": "test",
                "category_id": "111111111",
                "guild_id": "999999999",
            },
            # missing both category_id and guild_id
            {
                "channel_id": "222222222",
                "channel_name": "test2",
                "channel_type": "TEXT",
            },
        ]
        response = self.client.post(self.url, invalid_channels, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_type_channels = self.initial_channels + [
            {
                "channel_id": "111111111",
                "channel_name": "test",
                "category_id": "111111111",
                "channel_type": "INVALID_TYPE",
                "guild_id": "999999999",
            }
        ]
        response = self.client.post(self.url, invalid_type_channels, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # no changes were made during invalid requests
        self.assertEqual(DiscordChannel.objects.count(), len(self.initial_channels))

    def test_empty_channel_list(self):
        """Test syncing with an empty channel list (delete all)"""
        # Arrange
        empty_channels = []

        # Act
        response = self.client.post(self.url, empty_channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        changes = response.json()["changes"]
        self.assertEqual(changes["created"], 0)
        self.assertEqual(changes["updated"], 0)
        self.assertEqual(changes["deleted"], len(self.initial_channels))
        self.assertEqual(DiscordChannel.objects.count(), 0)

    def test_duplicate_channel_ids_in_request(self):
        """Test that duplicate channel IDs in request are rejected"""
        # Arrange
        duplicate_channels = [
            self.initial_channels[0],
            self.initial_channels[0],  # duplicate
        ]

        # Act
        response = self.client.post(self.url, duplicate_channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Duplicate channel IDs", response.json()["error"])

    def test_invalid_data_format_not_list(self):
        """Test that non-list data format is rejected"""
        # Arrange
        invalid_data = {"channel_id": "123456789"}

        # Act
        response = self.client.post(self.url, invalid_data, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Expected a list", response.json()["error"])

    def test_string_channel_ids(self):
        """Test that string channel IDs are properly converted"""
        # Arrange
        channels_with_string_ids = [
            {
                "channel_id": "123456789",  # string instead of int
                "channel_name": "test",
                "category_id": "111111111",  # string instead of int
                "channel_type": "TEXT",
                "guild_id": "999999999",  # string instead of int
            }
        ]

        # Act
        response = self.client.post(self.url, channels_with_string_ids, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        channel = DiscordChannel.objects.get(channel_id=123456789)
        self.assertEqual(channel.category_id, 111111111)
        self.assertEqual(channel.guild_id, 999999999)

    def test_null_category_id(self):
        """Test that null category_id is handled correctly"""
        # Arrange
        channels = [
            {
                "channel_id": "123456789",
                "channel_name": "test",
                "category_id": None,  # null value
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        channel = DiscordChannel.objects.get(channel_id=123456789)
        self.assertIsNone(channel.category_id)

    def test_invalid_channel_id_format(self):
        """Test that invalid channel ID format is rejected"""
        # Arrange
        invalid_channels = [
            {
                "channel_id": "not-a-number",
                "channel_name": "test",
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
        ]

        # Act
        response = self.client.post(self.url, invalid_channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthorized_access_without_api_key(self):
        """Test that requests without API key are rejected"""
        # Arrange
        self.client.credentials()  # Remove API key

        # Act
        response = self.client.post(self.url, self.initial_channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_large_batch_sync(self):
        """Test syncing a large batch of channels"""
        # Arrange
        large_batch = [
            {
                "channel_id": str(i),
                "channel_name": f"channel-{i}",
                "category_id": str(i % 10),
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
            for i in range(100)
        ]

        # Act
        response = self.client.post(self.url, large_batch, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DiscordChannel.objects.count(), 100)


class DiscordChannelsMetadataTests(APITestCase):
    """Test DiscordChannelsMetadata view"""

    def setUp(self):
        """Set up test data and authentication"""
        # Create admin user
        self.user = User.objects.create_user(
            username="testadmin",
            password="testpass123",
            discord_username="testdiscord",
            email="admin@example.com",
        )
        self.admin_group = Group.objects.create(name="is_admin")
        self.user.groups.add(self.admin_group)
        self.client.force_authenticate(user=self.user)

        self.url = reverse("discord-channels-metadata")

        # Create test channels
        self.channels = [
            DiscordChannel.objects.create(
                channel_id=123456789,
                channel_name="general",
                category_id=111111111,
                channel_type="TEXT",
                guild_id=999999999,
            ),
            DiscordChannel.objects.create(
                channel_id=987654321,
                channel_name="voice-chat",
                category_id=111111111,
                channel_type="VOICE",
                guild_id=999999999,
            ),
            DiscordChannel.objects.create(
                channel_id=456789123,
                channel_name="announcements",
                category_id=222222222,
                channel_type="TEXT",
                guild_id=888888888,
            ),
        ]

    def test_get_all_channels(self):
        """Test getting all channels without filters"""
        # Act
        response = self.client.get(self.url)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 3)

    def test_filter_by_channel_type(self):
        """Test filtering channels by type"""
        # Act
        response = self.client.get(self.url, {"type": "TEXT"})

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertTrue(all(ch["channel_type"] == "TEXT" for ch in data))

    def test_filter_by_channel_id(self):
        """Test filtering channels by channel_id"""
        # Act
        response = self.client.get(self.url, {"channel_id": "123456789"})

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["channel_id"], 123456789)

    def test_filter_by_category_id(self):
        """Test filtering channels by category_id"""
        # Act
        response = self.client.get(self.url, {"category_id": "111111111"})

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertTrue(all(ch["category_id"] == 111111111 for ch in data))

    def test_filter_by_guild_id(self):
        """Test filtering channels by guild_id"""
        # Act
        response = self.client.get(self.url, {"guild_id": "888888888"})

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["guild_id"], 888888888)

    def test_no_channels_found(self):
        """Test when no channels match the filter"""
        # Act
        response = self.client.get(self.url, {"channel_id": "999999999999"})

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 0)

    def test_unauthorized_access(self):
        """Test that non-admin users cannot access metadata"""
        # Arrange
        self.client.force_authenticate(user=None)

        # Act
        response = self.client.get(self.url)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DiscordChannelsAntiEntropyEdgeCasesTests(APITestCase):
    """Additional edge case tests for DiscordChannelsAntiEntropy view"""

    def setUp(self):
        """Set up test data and authentication"""
        api_key, key = APIKey.objects.create_key(name="swecc-bot")
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
        self.url = reverse("discord-channels-sync")

    def test_category_id_as_integer_zero(self):
        """Test that category_id of 0 is handled correctly"""
        # Arrange
        channels = [
            {
                "channel_id": "123456789",
                "channel_name": "test",
                "category_id": 0,
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        channel = DiscordChannel.objects.get(channel_id=123456789)
        self.assertEqual(channel.category_id, 0)

    def test_multiple_guilds(self):
        """Test syncing channels from multiple guilds"""
        # Arrange
        channels = [
            {
                "channel_id": str(i),
                "channel_name": f"channel-{i}",
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": str(i % 3),  # 3 different guilds
            }
            for i in range(9)
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DiscordChannel.objects.count(), 9)
        # Verify different guilds
        guild_ids = set(DiscordChannel.objects.values_list("guild_id", flat=True))
        self.assertEqual(len(guild_ids), 3)

    def test_all_channel_types_in_one_sync(self):
        """Test syncing all channel types in a single request"""
        # Arrange
        channel_types = ["TEXT", "VOICE", "CATEGORY", "STAGE", "FORUM"]
        channels = [
            {
                "channel_id": str(i),
                "channel_name": f"{channel_type.lower()}-channel",
                "category_id": "111111111",
                "channel_type": channel_type,
                "guild_id": "999999999",
            }
            for i, channel_type in enumerate(channel_types)
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DiscordChannel.objects.count(), 5)
        # Verify all types exist
        types_in_db = set(DiscordChannel.objects.values_list("channel_type", flat=True))
        self.assertEqual(types_in_db, set(channel_types))

    def test_update_only_one_field(self):
        """Test updating only one field of a channel"""
        # Arrange
        DiscordChannel.objects.create(
            channel_id=123456789,
            channel_name="original",
            category_id=111111111,
            channel_type="TEXT",
            guild_id=999999999,
        )
        updated_channels = [
            {
                "channel_id": "123456789",
                "channel_name": "updated",  # only name changed
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
        ]

        # Act
        response = self.client.post(self.url, updated_channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        changes = response.json()["changes"]
        self.assertEqual(changes["updated"], 1)
        channel = DiscordChannel.objects.get(channel_id=123456789)
        self.assertEqual(channel.channel_name, "updated")

    def test_special_characters_in_channel_name(self):
        """Test channel names with special characters"""
        # Arrange
        channels = [
            {
                "channel_id": "123456789",
                "channel_name": "test-channel_123!@#",
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        channel = DiscordChannel.objects.get(channel_id=123456789)
        self.assertEqual(channel.channel_name, "test-channel_123!@#")

    def test_invalid_guild_id_format(self):
        """Test that invalid guild_id format is rejected"""
        # Arrange
        channels = [
            {
                "channel_id": "123456789",
                "channel_name": "test",
                "category_id": "111111111",
                "channel_type": "TEXT",
                "guild_id": "invalid",
            }
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_category_id_format(self):
        """Test that invalid category_id format is rejected"""
        # Arrange
        channels = [
            {
                "channel_id": "123456789",
                "channel_name": "test",
                "category_id": "invalid",
                "channel_type": "TEXT",
                "guild_id": "999999999",
            }
        ]

        # Act
        response = self.client.post(self.url, channels, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
