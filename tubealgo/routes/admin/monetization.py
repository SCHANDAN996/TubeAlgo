# tubealgo/routes/admin/monetization.py

from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import Payment, Coupon, SubscriptionPlan
# <<< बदलाव यहाँ है: PlanForm को SubscriptionPlanForm से बदला गया >>>
from ...forms import CouponForm, SubscriptionPlanForm # Was PlanForm

@admin_bp.route('/payments')
@login_required
@admin_required
def payments():
    page = request.args.get('page', 1, type=int)
    try:
        pagination = Payment.query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20)
        return render_template('admin/payments.html', pagination=pagination)
    except Exception as e:
        current_app.logger.error(f"Error loading payments: {str(e)}", exc_info=True)
        flash("Error loading payment history.", "error")
        from flask_sqlalchemy.pagination import Pagination
        pagination = Pagination(None, 1, 20, 0, [])
        return render_template('admin/payments.html', pagination=pagination)


@admin_bp.route('/coupons')
@login_required
@admin_required
def coupons():
    try:
        all_coupons = Coupon.query.order_by(Coupon.id.desc()).all()
        return render_template('admin/coupons.html', coupons=all_coupons)
    except Exception as e:
        current_app.logger.error(f"Error loading coupons: {str(e)}", exc_info=True)
        flash("Error loading coupons.", "error")
        return render_template('admin/coupons.html', coupons=[])


@admin_bp.route('/coupons/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_coupon():
    form = CouponForm()
    if form.validate_on_submit():
        try:
            new_coupon = Coupon(
                code=form.code.data.upper(),
                discount_type=form.discount_type.data,
                discount_value=form.discount_value.data,
                max_uses=form.max_uses.data,
                valid_until=form.valid_until.data,
                is_active=form.is_active.data # Make sure is_active is included
            )
            # Add logic for applicable_plans if needed
            db.session.add(new_coupon)
            db.session.commit()
            flash(f"Coupon '{new_coupon.code}' created successfully!", 'success')
            return redirect(url_for('admin.coupons'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating coupon: {str(e)}", exc_info=True)
            flash(f"Error creating coupon: {str(e)}", "error")
    # Pass form for GET or validation failure
    return render_template('admin/create_coupon.html', form=form, legend='Create New Coupon')


@admin_bp.route('/coupons/edit/<int:coupon_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    form = CouponForm(obj=coupon) # Populate form with existing data
    if form.validate_on_submit():
        try:
            coupon.code = form.code.data.upper()
            coupon.discount_type = form.discount_type.data
            coupon.discount_value = form.discount_value.data
            coupon.max_uses = form.max_uses.data
            coupon.valid_until = form.valid_until.data
            coupon.is_active = form.is_active.data # Update is_active
            # Add logic for applicable_plans if needed
            db.session.commit()
            flash(f"Coupon '{coupon.code}' updated successfully!", 'success')
            return redirect(url_for('admin.coupons'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing coupon {coupon_id}: {str(e)}", exc_info=True)
            flash(f"Error updating coupon: {str(e)}", "error")
    # Pass form for GET or validation failure
    return render_template('admin/create_coupon.html', form=form, legend=f"Edit Coupon: {coupon.code}")


@admin_bp.route('/plans')
@login_required
@admin_required
def plans():
    try:
        all_plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
        return render_template('admin/plans.html', plans=all_plans)
    except Exception as e:
        current_app.logger.error(f"Error loading plans: {str(e)}", exc_info=True)
        flash("Error loading subscription plans.", "error")
        return render_template('admin/plans.html', plans=[])


@admin_bp.route('/plans/edit/<int:plan_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_plan(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    # <<< बदलाव यहाँ है: PlanForm को SubscriptionPlanForm से बदला गया >>>
    form = SubscriptionPlanForm(obj=plan) # Use correct form name
    if form.validate_on_submit():
        try:
            # Update plan attributes from form
            form.populate_obj(plan) # Automatically update fields matching form names
            db.session.commit()
            flash(f"Plan '{plan.name}' updated successfully!", 'success')
            return redirect(url_for('admin.plans'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing plan {plan_id}: {str(e)}", exc_info=True)
            flash(f"Error updating plan: {str(e)}", "error")
    # Pass form for GET or validation failure
    return render_template('admin/edit_plan.html', form=form, plan=plan)
