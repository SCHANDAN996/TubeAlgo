# tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from tubealgo import db
from tubealgo.models import Payment, SubscriptionPlan, User
import requests
import json
from datetime import datetime, timedelta
import uuid

payment_bp = Blueprint('payment', __name__)

@payment_bp.route('/create_cashfree_order', methods=['POST'])
@login_required
def create_cashfree_order():
    try:
        data = request.get_json()
        plan_id = data.get('plan')
        phone_number = data.get('phone_number') # Frontend से फोन नंबर प्राप्त करें

        # फोन नंबर की वैलिडेशन
        if not phone_number or not phone_number.isdigit() or len(phone_number) < 10:
            return jsonify({'error': 'A valid 10-digit phone number is required.'}), 400

        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            return jsonify({'error': 'Invalid plan specified.'}), 400

        # अगर यूजर का फोन नंबर सेव नहीं है, तो इसे सेव करें
        if not current_user.phone_number:
            current_user.phone_number = phone_number
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Failed to save phone number for user {current_user.id}: {str(e)}")
                # अगर सेव करने में दिक्कत हो, तो भी पेमेंट जारी रखें, लेकिन लॉग करें
                pass # Continue with payment even if save fails, but log it.

        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')

        if not cashfree_app_id or not cashfree_secret_key:
            current_app.logger.error("Cashfree credentials are not configured.")
            return jsonify({'error': 'Payment gateway is not configured on the server.'}), 500

        base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"
        order_id = f"order_{current_user.id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"

        order_data = {
            "order_amount": plan.price / 100,
            "order_currency": "INR",
            "order_id": order_id,
            "customer_details": {
                "customer_id": str(current_user.id),
                "customer_email": current_user.email,
                "customer_phone": phone_number # प्राप्त फोन नंबर का उपयोग करें
            },
            "order_meta": {
                "return_url": url_for('payment.cashfree_verification', _external=True) + "?order_id={order_id}"
            }
        }

        headers = {
            'Content-Type': 'application/json',
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }

        response = requests.post(f"{base_url}/orders", headers=headers, data=json.dumps(order_data))

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('payment_session_id'):
                # पेमेंट रिकॉर्ड बनाएं
                payment = Payment(
                    user_id=current_user.id,
                    razorpay_payment_id="", # Cashfree के लिए खाली छोड़ें या cf_order_id बाद में डालें
                    razorpay_order_id=order_id, # हमारा बनाया हुआ ऑर्डर ID
                    amount=plan.price,
                    currency='INR',
                    plan_id=plan_id,
                    status='created' # Initial status
                )
                db.session.add(payment)
                db.session.commit()

                return jsonify({
                    'order_id': order_id,
                    'payment_session_id': response_data['payment_session_id']
                })
            else:
                current_app.logger.error("Cashfree OK response but no payment_session_id.")
                return jsonify({'error': 'Failed to create payment session from gateway.'}), 500
        else:
            error_msg = response.json().get('message', 'Failed to create order with payment gateway.')
            current_app.logger.error(f"Cashfree API error: {response.status_code} - {response.text}")
            return jsonify({'error': error_msg}), response.status_code

    except Exception as e:
        current_app.logger.error(f"Cashfree order creation exception: {str(e)}", exc_info=True)
        return jsonify({'error': 'An internal server error occurred during payment processing.'}), 500


@payment_bp.route('/cashfree_verification')
@login_required
def cashfree_verification():
    try:
        order_id = request.args.get('order_id')

        if not order_id:
            flash('Payment verification failed. Order ID not found.', 'error')
            return redirect(url_for('core.pricing'))

        # यूजर के पेमेंट रिकॉर्ड को खोजें
        payment = Payment.query.filter_by(razorpay_order_id=order_id, user_id=current_user.id).first()

        if not payment:
            flash('Payment record not found in our system.', 'error')
            return redirect(url_for('core.pricing'))

        # अगर पेमेंट पहले से ही कैप्चर हो चुका है, तो दोबारा प्रोसेस न करें
        if payment.status == 'captured':
             flash('Your subscription is already active.', 'info')
             return redirect(url_for('dashboard.dashboard'))

        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"

        headers = {
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }

        # Cashfree से ऑर्डर की स्थिति प्राप्त करें
        order_response = requests.get(f"{base_url}/orders/{order_id}", headers=headers)

        if order_response.status_code == 200:
            order_data = order_response.json()
            actual_payment_status = order_data.get('order_status', '').upper()

            # सफल पेमेंट की स्थिति जांचें
            if actual_payment_status in ['PAID', 'SUCCESS']:
                # यूजर का प्लान और एक्सपायरी डेट अपडेट करें
                current_user.subscription_plan = payment.plan_id
                current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                payment.status = 'captured'
                # Cashfree की ऑर्डर ID या पेमेंट ID सेव करें (वैकल्पिक)
                payment.razorpay_payment_id = order_data.get('cf_order_id', order_id) # cf_order_id को पेमेंट ID की तरह इस्तेमाल करें
                db.session.commit()
                flash('Payment successful! Your subscription has been activated for 30 days.', 'success')
                return redirect(url_for('dashboard.dashboard'))
            else:
                # असफल पेमेंट
                payment.status = actual_payment_status.lower() if actual_payment_status else 'failed'
                db.session.commit()
                flash(f'Payment {payment.status}. Please try again or contact support.', 'error')
                return redirect(url_for('core.pricing'))
        else:
            # Cashfree API से स्थिति जांचने में विफल
            current_app.logger.error(f"Cashfree verification API error for order {order_id}: {order_response.status_code} - {order_response.text}")
            flash('Could not verify payment status with the gateway. Please contact support.', 'error')
            return redirect(url_for('core.pricing'))

    except Exception as e:
        current_app.logger.error(f"Cashfree verification exception: {str(e)}", exc_info=True)
        flash('Payment verification failed due to an unexpected error.', 'error')
        return redirect(url_for('core.pricing'))

@payment_bp.route('/cashfree_webhook', methods=['POST'])
def cashfree_webhook():
    # नोट: Webhook सुरक्षा (signature verification) यहाँ लागू नहीं की गई है, प्रोडक्शन के लिए ज़रूरी है।
    try:
        webhook_data = request.get_json()
        current_app.logger.info(f"Received Cashfree webhook: {webhook_data}") # Webhook डेटा लॉग करें

        event_type = webhook_data.get('type')

        # केवल सफल पेमेंट इवेंट्स को प्रोसेस करें
        if event_type and 'order.success' in event_type.lower():
            order_id = webhook_data.get('data', {}).get('order', {}).get('order_id')
            payment_status = webhook_data.get('data', {}).get('order', {}).get('order_status', '').upper()
            cf_order_id = webhook_data.get('data', {}).get('order', {}).get('cf_order_id') # Cashfree ऑर्डर ID

            if payment_status in ['PAID', 'SUCCESS'] and order_id:
                payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
                if payment and payment.status != 'captured':
                    user = User.query.get(payment.user_id)
                    if user:
                        user.subscription_plan = payment.plan_id
                        user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                        payment.status = 'captured'
                        payment.razorpay_payment_id = str(cf_order_id) # Cashfree ID सेव करें
                        db.session.commit()
                        current_app.logger.info(f"Webhook processed successfully for order {order_id}")
                    else:
                        current_app.logger.warning(f"Webhook: User not found for payment order {order_id}")
                elif payment and payment.status == 'captured':
                     current_app.logger.info(f"Webhook: Order {order_id} already captured, skipping.")
                else:
                    current_app.logger.warning(f"Webhook: Payment record not found for order {order_id}")
            else:
                 current_app.logger.info(f"Webhook: Ignoring non-success status '{payment_status}' for order {order_id}")
        else:
             current_app.logger.info(f"Webhook: Ignoring event type '{event_type}'")


        return jsonify({'status': 'success'}), 200

    except Exception as e:
        current_app.logger.error(f"Cashfree webhook error: {str(e)}", exc_info=True)
        return jsonify({'status': 'error'}), 500