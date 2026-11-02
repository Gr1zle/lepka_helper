from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from delivery_settings import getSettings, saveSettings
from notification_mail import status


class DeliveryInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    deviceEnabled: bool
    likes: bool
    comments: bool
    replies: bool
    awards: bool
    projects: bool
    learning: bool
    emailEnabled: bool


def installDeliveryRoutes(app,currentUser):
    @app.get('/account/notification-delivery')
    def get(user=Depends(currentUser)):
        return dict(data=dict(settings=getSettings(user['userId']),mail=status(user['userId'])))

    @app.put('/account/notification-delivery')
    def save(data:DeliveryInput,user=Depends(currentUser)):
        return dict(data=dict(settings=saveSettings(user['userId'],data.model_dump()),mail=status(user['userId'])))
