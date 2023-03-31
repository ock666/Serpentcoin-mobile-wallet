from kivy.app import App
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout
import hashlib
import binascii
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle
from kivy.clock import Clock
from kivy.uix.image import Image
import qrcode
from Crypto.PublicKey import RSA
import io
from kivy_garden.xcamera import XCamera
from datetime import datetime
import os
import json
from src.utilities import Write, Generate
from src.validation import Funds, ValidChain
from time import time
import pydenticon
import requests
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15


class Setup:
    def __init__(self):
        # chain request
        chain_response = requests.get(f'http://192.168.0.250:5000/chain')
        if chain_response.status_code == 200:
            chain = chain_response.json()['chain']

            if ValidChain.valid_chain(chain):
                new_chain = chain

        if new_chain:
            self.chain = new_chain

            if os.path.exists('data/chain.json'):
                os.remove('data/chain.json')

            with open('data/chain.json', 'w') as f:
                for i in self.chain:
                    string = json.dumps(i)
                    f.write(string)
                    f.write('\n')




        s = open('data/chain.json', 'r')
        for line in s.readlines():
            try:
                j = line.split('|')[-1]
                self.chain.append(json.loads(j))

            except ValueError:
                print("the json is rekt slut")
                continue

        if not os.path.isfile('data/wallet.json'):
            print('generating wallet...')
            Generate.generate_wallet()
            print('done')

        # attempting to open wallet file
        wallet_file = json.load(open('data/wallet.json', 'r'))
        self.private_key = RSA.import_key(wallet_file['private key'])
        self.public_key = RSA.import_key(wallet_file['public key'])
        self.public_key_hex = wallet_file['public key hex']
        self.public_key_hash = wallet_file['public key hash']

        print("Now validating local chain, please wait.")
        if ValidChain.valid_chain(self.chain):
            print("Chain is valid")
        else:
            print("Local chain is invalid, please sync the node with another upstream node.")

        #check to see if we have a wallet address qr present
        if not os.path.isfile('data/wallet_qr.png'):
            ## if not creates qr code for receive screen
            data = self.public_key_hash
            qr = qrcode.QRCode(
                version=1,
                box_size=10,
                border=2)

            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')
            img.save('data/wallet_qr.png')

        generator = pydenticon.Generator(5, 5)
        identicon = generator.generate(wallet_file['public key hash'], 240, 240)
        with open('data/identicon.png', 'wb') as f:
            f.write(identicon)


class TransactionField(BoxLayout):
    def __init__(self, field_name, field_value, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.add_widget(Label(text=field_name, size_hint=(0.5, 1)))
        self.add_widget(Label(text=field_value, size_hint=(0.5, 1)))

class TransactionScreen(Screen):
    def __init__(self, transaction_data, **kwargs):
        super(TransactionScreen, self).__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')

        if transaction_data:
            for key, value in transaction_data.items():
                if key not in ["public_key_hex", "signature"]:
                    layout.add_widget(TransactionField(field_name=key, field_value=str(value)))

        else:
            layout.add_widget(Label(text="No transaction data available."))

        back_button = Button(text="Back to balance", size_hint_y=None, height=dp(40))
        back_button.bind(on_press=self.go_to_balance)
        layout.add_widget(back_button)

        self.add_widget(layout)

    def go_to_balance(self, instance):
        self.manager.current = 'balance'


class TransactionBox(BoxLayout):
    def __init__(self, transaction, **kwargs):
        if not transaction:
            # Handle empty or None values
            return

        if not isinstance(transaction, dict):
            # Handle non-dictionary values
            return
        wallet_file = json.load(open('data/wallet.json', 'r'))
        address = wallet_file['public key hash']
        self.transaction_data = transaction
        super(TransactionBox, self).__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(50)
        with self.canvas:
            Color(0.6, 0.6, 0.6, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(pos=self.update_rect, size=self.update_rect)

        # Create image widget for indicating whether the transaction is sent or received
        image_src = 'data/sent.png' if transaction['sender'] == address else 'data/received.png'
        image = Image(source=image_src, size_hint_x=0.1)

        # create sender/receiver widget for indictating whether to display the sender or the recipient
        date_label_text = "..." + transaction['recipient'][-8:] if transaction['sender'] == address or 'Coinbase Reward' else "..." + transaction['sender'][-8:]

        date_label = Label(text=date_label_text, size_hint_x=0.2)
        desc_label = Label(
            text=str(datetime.fromtimestamp(int(transaction['time_submitted'])).strftime('%H:%M:%S %d/%m/%Y')),
            size_hint_x=0.6)
        amount_label = Label(text=str(transaction['amount']), size_hint_x=0.1)

        # Add the image widget to the beginning of the layout
        self.add_widget(image)
        self.add_widget(date_label)
        self.add_widget(desc_label)
        self.add_widget(amount_label)


    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            # Open a new screen and display transaction data as a string
            screen_manager = self.get_parent_window().children[0]
            screen_name = 'transaction-data-screen_' + self.transaction_data['transaction_hash'][-8:]
            screen = TransactionScreen(name=screen_name, transaction_data=self.transaction_data)
            label = Label(text=str(self.transaction_data))
            screen.add_widget(label)
            screen_manager.add_widget(screen)
            screen_manager.current = screen_name
            return True
        return super(TransactionBox, self).on_touch_down(touch)


class BalanceScreen(Screen):
    def __init__(self, **kwargs):
        self.chain = []
        # create data dir if it does not exist
        if not os.path.exists('data'):
            print('creating data directory')
            os.makedirs('data')

        if not os.path.isfile('data/chain.json'):
            open('data/chain.json', 'w')

        s = open('data/chain.json', 'r')
        for line in s.readlines():
            try:
                j = line.split('|')[-1]
                self.chain.append(json.loads(j))

            except ValueError:
                print("the json is rekt slut")
                continue


        wallet_file = json.load(open('data/wallet.json', 'r'))


        identicon = Image(source='data/identicon.png')

        self.more_button = Button(text="Load More Transactions", size_hint_y=None, height=dp(50))

        self.address = wallet_file['public key hash']
        super(BalanceScreen, self).__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')


        balance_float = Label(text=str(float(Funds.enumerate_funds(self.address, self.chain))) + " XSC")

        self.balance_float  = balance_float

        layout.add_widget(identicon)
        layout.add_widget(balance_float)
        # Add scrollable transaction history
        scrollview = ScrollView()
        self.history_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.history_layout.bind(minimum_height=self.history_layout.setter('height'))

        sent = []
        received = []
        transactions = []

        for block in self.chain:
            for transaction in block['transactions']:
                # code to find received transactions
                if transaction['recipient'] == self.address:
                    received.append(transaction)
                    transactions.append(transaction)
                # code to find sent transactions
                if transaction['sender'] == self.address:
                    sent.append(transaction)
                    transactions.append(transaction)
                else:
                    continue

        # Reverse the list of transactions to show the most recent one at the top
        transactions.reverse()

        added_transactions = set()

        for transaction in transactions[:-25]:
            if transaction['transaction_hash'] not in added_transactions:
                transaction_box = TransactionBox(transaction)
                self.history_layout.add_widget(transaction_box)
                added_transactions.add(transaction['transaction_hash'])

        # Add More button at the end
        more_button = Button(text='More...', size_hint_y=None, height=dp(50))
        more_button.bind(on_press=self.show_full_history)
        self.history_layout.add_widget(more_button)

        scrollview.add_widget(self.history_layout)
        layout.add_widget(scrollview)

        # Add buttons horizontally
        buttons_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50))
        buttons_layout.add_widget(Button(text='Send Transaction', size_hint_x=0.33, on_press=self.go_to_send))
        buttons_layout.add_widget(Button(text='Contact Book', size_hint_x=0.33))
        buttons_layout.add_widget(Button(text='Receive Transaction', size_hint_x=0.33, on_press=self.go_to_receive))
        layout.add_widget(buttons_layout)

        self.add_widget(layout)
        self.balance_update = Clock.schedule_interval(self.update_balance, 60)
        self.transaction_update = Clock.schedule_interval(self.update_history, 60)


    def update_history(self, dt):
        print("updating history")
        # Clear the existing transaction history
        self.history_layout.clear_widgets()

        # Get the latest transactions
        sent = []
        received = []
        transactions = []

        for block in self.chain:
            for transaction in block['transactions']:
                if transaction['recipient'] == self.address:
                    received.append(transaction)
                    transactions.append(transaction)
                elif transaction['sender'] == self.address:
                    sent.append(transaction)
                    transactions.append(transaction)

        # Reverse the list of transactions to show the most recent one at the top
        transactions.reverse()

        added_transactions = set()

        # Create TransactionBox widgets for each transaction and add them to the history layout
        for transaction in transactions:
            if transaction['transaction_hash'] not in added_transactions:
                transaction_box = TransactionBox(transaction)
                self.history_layout.add_widget(transaction_box)
                added_transactions.add(transaction['transaction_hash'])

    def update_balance(self, dt):
        print("updating balance")
        address = json.load(open('data/wallet.json', 'r'))['public key hash']
        # chain request
        chain_response = requests.get(f'http://192.168.0.250:5000/chain')
        if chain_response.status_code == 200:
            chain = chain_response.json()['chain']

            if ValidChain.valid_chain(chain):
                new_chain = chain

        if new_chain:
            self.chain = new_chain

            if os.path.exists('data/chain.json'):
                os.remove('data/chain.json')

            with open('data/chain.json', 'w') as f:
                for i in self.chain:
                    string = json.dumps(i)
                    f.write(string)
                    f.write('\n')

        self.chain = []  # initialize self.chain to an empty list
        s = open('data/chain.json', 'r')
        for line in s.readlines():
            try:
                j = line.split('|')[-1]
                self.chain.append(json.loads(j))

            except ValueError:
                print("the json is rekt slut")
                continue
        self.balance_float.text = str(float(Funds.enumerate_funds(address, self.chain))) + " XSC"
        print("balance is: ", self.balance_float.text)

    def show_full_history(self, instance):
        # TODO: implement full transaction history view
        pass

    def go_to_send(self, instance):
        self.manager.current = 'send'

    def go_to_receive(self, instance):
        self.manager.current = 'receive'

class SendScreen(Screen):
    def __init__(self, **kwargs):
        super(SendScreen, self).__init__(**kwargs)

        # create layout
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.add_widget(layout)

        # add widgets to layout
        layout.add_widget(Label(text='Send Transaction', size_hint=(1, 0.1)))

        input_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint=(1, 0.4))
        layout.add_widget(input_layout)

        self.address_input = TextInput(hint_text='Enter Address', size_hint=(0.8, None), height=30)
        input_layout.add_widget(self.address_input)
        input_layout.add_widget(Button(text='Camera', size_hint=(0.2, None), height=30, on_press=self.open_camera))

        self.amount_input = TextInput(hint_text='Enter Amount', size_hint=(1, None), height=30)
        input_layout.add_widget(self.amount_input)

        button_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint=(1, 0.1))
        layout.add_widget(button_layout)

        button_layout.add_widget(Button(text='Send', size_hint=(0.5, 1), on_press=self.confirm_transaction))

        button_layout.add_widget(Button(text='Back', size_hint=(0.5, 1), on_press=self.go_to_balance))

    def confirm_transaction(self, transaction):
        # create the popup
        transaction_data = {
            'recipient': str(self.address_input.text),
            'amount': str(self.amount_input.text)
        }

        content = BoxLayout(orientation='vertical')
        content.add_widget(Label(text='Are you sure you want to send the following transaction?'))
        content.add_widget(Label(text='Recipient: ' + transaction_data['recipient']))
        content.add_widget(Label(text='Amount: ' + transaction_data['amount']))
        buttons = BoxLayout(orientation='horizontal')
        yes_button = Button(text='Yes')
        no_button = Button(text='No')
        yes_button.bind(on_press=lambda x: self.send_transaction())
        yes_button.bind(on_release=lambda x: popup.dismiss())
        no_button.bind(on_press=lambda x: popup.dismiss())
        buttons.add_widget(yes_button)
        buttons.add_widget(no_button)
        content.add_widget(buttons)

        popup = Popup(title='Confirm Transaction', content=content, size_hint=(0.7, 0.3))
        popup.bind(on_dismiss=lambda x: self.go_to_balance(None))
        popup.open()

    def go_to_balance(self, instance):
        self.manager.current = 'balance'

    def send_transaction(self):
        wallet = json.load(open('data/wallet.json', 'r'))
        sender = wallet['public key hash']
        recipient = self.address_input.text
        amount = self.amount_input.text
        public_key_hex = wallet['public key hex']
        unix_time = time()
        previous_block_hash = self.get_last_block_hash()

        trans_data = {
            'sender': sender,
            'recipient': recipient,
            'amount': float(amount),
            'time_submitted': unix_time,
            'previous_block_hash': previous_block_hash,
            'public_key_hex': public_key_hex
        }
        total_bytes = self.calculate_bytes(trans_data)
        fee = self.calculate_fee(total_bytes)

        transaction = {
            'sender': sender,
            'recipient': recipient,
            'amount': float(amount),
            'fee': float(fee),
            'time_submitted': unix_time,
            'previous_hash': previous_block_hash,
            'public_key_hex': public_key_hex
        }

        hashed_trans = self.hash(transaction)

        trans_with_hash = {
            'sender': sender,
            'recipient': recipient,
            'amount': float(amount),
            'fee': float(fee),
            'time_submitted': trans_data['time_submitted'],
            'previous_hash': previous_block_hash,
            'public_key_hex': public_key_hex,
            'transaction_hash': hashed_trans
        }

        signed_trans = self.sign(trans_with_hash)

        full_transaction = {
            'sender': sender,
            'recipient': recipient,
            'amount': float(amount),
            'fee': float(fee),
            'time_submitted': trans_data['time_submitted'],
            'previous_hash': previous_block_hash,
            'public_key_hex': public_key_hex,
            'transaction_hash': hashed_trans,
            'signature': signed_trans
        }



        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        response = requests.post(f'http://192.168.0.250:5000/transactions/new', json=full_transaction, headers=headers)
        if response.status_code == 201:
            print(f"Sending {amount} to {recipient}")

    def sign(self, data):
        signature_hex = binascii.hexlify(self.sign_transaction_data(data)).decode("utf-8")
        return signature_hex

    def sign_transaction_data(self, data):
        wallet = json.load(open('data/wallet.json', 'r'))
        private_key = RSA.import_key(wallet['private key'])
        transaction_bytes = json.dumps(data, sort_keys=True).encode('utf-8')
        hash_object = SHA256.new(transaction_bytes)
        signature = pkcs1_15.new(private_key).sign(hash_object)
        return signature

    def go_to_balance(self, instance):
        self.manager.current = 'balance'

    def open_camera(self, instance):
        # TODO: Implement open camera functionality using XCamera
        pass

    # hash functions
    @staticmethod
    def hash(data):
        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        data_string = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(data_string).hexdigest()

    def get_last_block_hash(self):
        response = requests.get(f'http://192.168.0.250:5000/chain')

        if response.status_code == 200:
            length = response.json()['length']
            chain = response.json()['chain']
            return chain[length - 1]['block_hash']

    def calculate_bytes(self, transaction):
        tx_string = json.dumps(transaction)
        tx_bytes = tx_string.encode('ascii')
        return len(tx_bytes)

    def calculate_fee(self, tx_bytes_length):
        per_kb_fee = 0.25
        sig_hash_bytes = 800
        total = tx_bytes_length + sig_hash_bytes
        return (total / 1000) * per_kb_fee


class ConfirmationScreen(Screen):
    def __init__(self, transaction_data, **kwargs):
        super(ConfirmationScreen, self).__init__(**kwargs)

        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.add_widget(layout)

        layout.add_widget(Label(text='Confirm Transaction', size_hint=(1, 0.1)))

        data_layout = GridLayout(cols=2, spacing=10, size_hint=(1, 0.6))
        layout.add_widget(data_layout)

        data_layout.add_widget(Label(text='Recipient:'))
        data_layout.add_widget(Label(text=transaction_data['recipient']))

        data_layout.add_widget(Label(text='Amount:'))
        data_layout.add_widget(Label(text=str(transaction_data['amount'])))

        data_layout.add_widget(Label(text='Fee:'))
        data_layout.add_widget(Label(text=str(transaction_data['fee'])))

        button_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint=(1, 0.1))
        layout.add_widget(button_layout)

        button_layout.add_widget(Button(text='Confirm', size_hint=(0.5, 1), on_press=self.confirm_transaction))
        button_layout.add_widget(Button(text='Cancel', size_hint=(0.5, 1), on_press=self.cancel_transaction))

        self.transaction_data = transaction_data

    def confirm_transaction(self, instance):
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        response = requests.post(f'http://192.168.0.250:5000/transactions/new', json=self.transaction_data, headers=headers)
        if response.status_code == 201:
            print(f"Sending {self.transaction_data['amount']} to {self.transaction_data['recipient']}")
        self.manager.current = 'balance'

    def cancel_transaction(self, instance):
        self.manager.current = 'send'


class ReceiveScreen(Screen):
    def __init__(self, **kwargs):
        super(ReceiveScreen, self).__init__(**kwargs)
        wallet_file = json.load(open('data/wallet.json', 'r'))
        layout = BoxLayout(orientation='vertical')
        layout.add_widget(Label(text='Receive Transaction', size_hint_y=None))
        self.qr_image = Image(source='data/wallet_qr.png')
        self.address_label = Label(text=wallet_file['public key hash'],
                                       size_hint_y=None, height=dp(30))
        layout.add_widget(self.qr_image)
        layout.add_widget(self.address_label)
        button_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=dp(50))
        button_layout.add_widget(Button(text='Back', on_press=self.go_to_balance, size_hint=(0.3, 1), halign='center', valign='middle'))
        layout.add_widget(button_layout)
        self.add_widget(layout)


    def go_to_balance(self, instance):
        self.manager.current = 'balance'





class MyKivyApp(App):
    def build(self):
        setup = Setup()
        sm = ScreenManager()
        balance_screen = BalanceScreen(name='balance')
        send_screen = SendScreen(name='send')
        receive_screen = ReceiveScreen(name='receive')

        sm.add_widget(balance_screen)
        sm.add_widget(send_screen)
        sm.add_widget(receive_screen)
        return sm


if __name__ == '__main__':
    MyKivyApp().run()
