"""Instance-wide display preferences. Pins never confer model availability."""
import json


def validate_pins(pins):
    if not isinstance(pins, list) or len(pins) > 100:
        raise ValueError('Expected at most 100 model pins')
    result = []
    for pin in pins:
        if not isinstance(pin, str) or not pin.strip() or len(pin) > 1025 or '/' not in pin or any(ord(char) < 32 or ord(char) == 127 for char in pin):
            raise ValueError('Invalid provider/model pin')
        provider, model = pin.split('/', 1)
        if not provider.strip() or not model.strip() or len(provider) > 512 or len(model) > 512:
            raise ValueError('Invalid provider/model pin')
        if pin not in result:
            result.append(pin)
    return result


class ModelPreferences:
    def __init__(self, database):
        self.db = database

    async def get(self):
        async with self.db._connection.execute('SELECT pins FROM model_preferences WHERE singleton=1') as cursor:
            row = await cursor.fetchone()
        return {'pins': validate_pins(json.loads(row[0])) if row else []}

    async def set_pins(self, pins):
        pins = validate_pins(pins)
        async with self.db.transaction():
            await self.db._connection.execute(
                'UPDATE model_preferences SET pins=? WHERE singleton=1', (json.dumps(pins),))
        return {'pins': pins}
