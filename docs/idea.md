# Basic App Structure

An app consists of the app logic and a provider, establishing basically the connection over which updates are sent.
Both parts are connected through a YDocument and take actions reactively upon applied changes:
The app logic updates the YDoc or reacts to changes.
The provider creates the YDoc updates and sends them over the provided connection or reads incoming messages and applies those updates to the YDoc, triggering the app logic again.
